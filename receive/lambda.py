import boto3
import csv
import os
import logging
import sys
import email
from datetime import datetime, timezone
from collections import namedtuple
from multiprocessing.dummy import Pool as ThreadPool


CSVRow = namedtuple('CSVRow', ['who', 'when', 'what', 'price'])
LOCAL_CSV_PATH   = '/tmp/{}'.format(os.getenv('csv_key'))
ALLOWED_SENDERS  = os.getenv('allowed_senders').split(',')
MAX_PERIOD_SPEND = float(os.getenv('max_period_spend'))


def get_logger():
    logger = logging.getLogger(__name__)
    for handler in logger.handlers:
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(module)s:%(lineno)s %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger()
sns = boto3.client('sns')
s3  = boto3.client('s3')
thread_pool = ThreadPool(5)


def _is_clean(record):
    """Returns True if and only if the email has passed certain spam filter checks, and
    if it's from an allowed sender, and False otherwise.

    :param record: nested dictionary; see http://docs.aws.amazon.com/ses/latest/DeveloperGuide/receiving-email-notifications-contents.html
    """
    receipt_dict  = record['ses']['receipt']
    receipt_keys_to_check = {
        '{}Verdict'.format(key_prefix)
        for key_prefix in {'spf', 'virus', 'spam'}
    }
    for key in receipt_keys_to_check:
        if receipt_dict[key]['status'] != 'PASS':
            return False
    if record['ses']['mail']['source'] not in ALLOWED_SENDERS:
        return False
    return True


def _get_message_id(record):
    """Pulls out the S3 key of the email corresponding to this record

    :param record: nested dictionary; see http://docs.aws.amazon.com/ses/latest/DeveloperGuide/receiving-email-notifications-contents.html
    """
    return record['ses']['mail']['messageId']


def _to_local_format(utc_timestamp):
    """Returns a readable local time string.

    :param utc_timestamp: UTC formatted time string.
    """
    dt = datetime.strptime(utc_timestamp, '%a, %d %b %Y %H:%M:%S %z')
    dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(tz=None)
    return dt.strftime('%b %d, %Y %I:%M:%S %p')


def _get_email_bytes(record):
    """Downloads the email from S3 given metadata. Returns raw bytes.

    :param record: nested dictionary; see http://docs.aws.amazon.com/ses/latest/DeveloperGuide/receiving-email-notifications-contents.html
    """
    message_id = _get_message_id(record)
    bucket = os.getenv('email_bucket')
    prefix = os.getenv('email_prefix')
    s3_key = '{}/{}'.format(prefix, message_id)
    logger.info(
        'Getting email from bucket {} with key {}'.format(bucket, s3_key)
    )
    s3_obj = s3.get_object(Bucket=bucket, Key=s3_key)
    s3_obj = s3_obj['Body']
    return s3_obj.read()


def _get_csv_rows(record):
    """Constructs and returns a CSVRow from email metadata.

    :param record: nested dictionary; see http://docs.aws.amazon.com/ses/latest/DeveloperGuide/receiving-email-notifications-contents.html
    """
    # read everything into memory, it's expected to be quite small
    message = email.message_from_bytes(_get_email_bytes(record))
    price = None
    for part in message.walk():
        # this algorithm is so fragile; see
        #
        #   https://docs.python.org/3/library/email-examples.html#examples-using-the-provisional-api
        maintype, subtype = part.get_content_maintype(), part.get_content_subtype()
        if maintype != 'text' or subtype != 'plain':
            continue
        price = part.get_payload()
        price = price.strip()
        try:
            price = float(price)
        except Exception as e:
            logger.info("Couldn't get price: {}".format(e))
        else:
            break
    if not price:
        raise Exception('No price found for message_id {}'.format(message_id))
    return CSVRow(
        message['From'], _to_local_format(message['Date']), message['Subject'], price)


def _download_csv():
    """Downloads the budget csv from S3."""
    s3.download_file(
        os.getenv('csv_bucket'),
        os.getenv('csv_key'),
        LOCAL_CSV_PATH
    )


def _update_csv(*csv_rows):
    """Writes updates to the local downloaded csv.

    :param *csv_rows: any number of CSVRow
    """
    logger.info('Updating local csv.')
    with open(LOCAL_CSV_PATH, 'a', newline='') as f:
        csv.writer(f).writerows(csv_rows)
    logger.info('Updated local csv.')


def _commit_csv():
    """Puts the updated downloaded csv back to S3."""
    if os.getenv('dry_run'):
        return
    logger.info('Committing csv.')
    with open(LOCAL_CSV_PATH, 'rb') as f:
        s3.put_object(
            Bucket=os.getenv('csv_bucket'),
            Key=os.getenv('csv_key'),
            Body=f,
        )
    logger.info('Committed csv.')


def _notify_update(csv_rows, period_spend):
    """Sends a summary to an SNS topic of what updates have been applied, what
    the current spend is for the period, and how much is remaining. If we're over
    the maximum spend for the period, we mention this.

    :param csv_rows: iterable of CSVRow
    :param period_spend:     float representing how much has been spent in this period (including csv_rows)
    """
    def get_message_line(csv_row):
        return ', '.join(
            list(csv_row[:-1]) + ['${:.2f}'.format(csv_row[-1])]
        )

    message_lines = list(map(get_message_line, csv_rows))
    message_lines.append('Total spend for period is now: ${:.2f}'.format(period_spend))
    delta = MAX_PERIOD_SPEND - period_spend
    if delta < 0:
        message_lines.append('You went ${:.2f} over budget!'.format(delta))
    else:
        message_lines.append('You have ${:.2f} remaining for the period.'.format(delta))
    message = os.linesep.join(message_lines)
    logger.info('Publishing update.')
    logger.info(message)
    sns.publish(TopicArn=os.getenv('sns_topic_arn'), Message=message)
    logger.info('Published update.')


def _get_period_spend(*csv_rows):
    """Sums all the prices in the price column of the csv.

    :param *csv_rows: any number of CSVRow
    """
    with open(LOCAL_CSV_PATH, newline='') as f:
        prices = [float(row['price']) for row in csv.DictReader(f)]
    return sum(prices)


def handler(event, *args):
    """Parses all sent emails, aggregates updates, downloads budget file from S3,
    writes updates to downloaded file, commits back to S3, and sends a notification.

    This isn't concurrency-safe, but we're expecting extremely little activity -
    three runs a day at most with no concurrency.

    :param event: see http://docs.aws.amazon.com/ses/latest/DeveloperGuide/receiving-email-notifications-contents.html
    """
    logger.info('Received event: {}'.format(event))
    records = [
        record for record in event['Records']
        if _is_clean(record)
    ]
    csv_rows = thread_pool.map(_get_csv_rows, records)
    logger.info('Got csv rows {}'.format(csv_rows))
    _download_csv()
    _update_csv(*csv_rows)
    _commit_csv()
    period_spend = _get_period_spend()
    _notify_update(csv_rows, period_spend)
    logger.info('Processed event.')


if __name__ == '__main__':
    event = {'Records': [{'eventSource': 'aws:ses', 'eventVersion': '1.0', 'ses': {'mail': {'timestamp': '2017-08-30T19:16:36.777Z', 'source': 'v.alvarez312@gmail.com', 'messageId': 'oei0v1srkdc7g0kckp27g3t327o94abgh7inci01', 'destination': ['budget@yangmillstheory.com'], 'headersTruncated': False, 'headers': [{'name': 'Return-Path', 'value': '<v.alvarez312@gmail.com>'}, {'name': 'Received', 'value': 'from mail-vk0-f46.google.com (mail-vk0-f46.google.com [209.85.213.46]) by inbound-smtp.us-west-2.amazonaws.com with SMTP id oei0v1srkdc7g0kckp27g3t327o94abgh7inci01 for budget@yangmillstheory.com; Wed, 30 Aug 2017 19:16:36 +0000 (UTC)'}, {'name': 'X-SES-Spam-Verdict', 'value': 'PASS'}, {'name': 'X-SES-Virus-Verdict', 'value': 'PASS'}, {'name': 'Received-SPF', 'value': 'pass (spfCheck: domain of _spf.google.com designates 209.85.213.46 as permitted sender) client-ip=209.85.213.46; envelope-from=v.alvarez312@gmail.com; helo=mail-vk0-f46.google.com;'}, {'name': 'Authentication-Results', 'value': 'amazonses.com; spf=pass (spfCheck: domain of _spf.google.com designates 209.85.213.46 as permitted sender) client-ip=209.85.213.46; envelope-from=v.alvarez312@gmail.com; helo=mail-vk0-f46.google.com; dkim=pass header.i=@gmail.com;'}, {'name': 'X-SES-RECEIPT', 'value': 'AEFBQUFBQUFBQUFHMVJjNWQxZ3cwd2x3WWxUYzJMSkZmSGNpT2MzUVhzYzJkU0ZVYStUcTRtVXhjSHAvY2dRTnFvSVF1TGFnRTQ2QjRScGZxSXBDcHpwc2VEOWxUdTAxekMvK0xNQityTGZGc29uRDliaVQwMit6bFpsRGRhODJCaVV1MEh4ZSs0cFpTaHVSbmsrbTdIcy92L1k1eU1aWlBkUWNaNmszL0hndWpQYjRDVHpobG5FZVNWZzVDeXRhNGpwZzhBT09HRyt4RkJCaGtwZGtpOEEzMFN3VVdFNytqU2RkOFhuQ0FjVU5lTmxYYlhGelhLYVZsWFZENm9rUkZUdmJBZXVpdmxucU93QVYzRm5ocUtqbS9tZE9LL1ZIeQ=='}, {'name': 'X-SES-DKIM-SIGNATURE', 'value': 'v=1; a=rsa-sha256; q=dns/txt; c=relaxed/simple; s=hsbnp7p3ensaochzwyq5wwmceodymuwv; d=amazonses.com; t=1504120597; h=X-SES-RECEIPT:MIME-Version:From:Date:Message-ID:Subject:To:Content-Type; bh=SEoUWjBEMpZ0/r4sgepX5xHgzXUOZcMlNJRetI5s6Is=; b=JBUQ3Yp9G4QL6X0K9aLm9ppuIW1+KWdc2x/XOun8LnlqlYJ8hHdEoDJ97fVE5o4T I4D6QqLfLujZhG0lftwKAZoJCkMFJYQTKjUB09dXsfJ35Y8VoGCOhgFmwvfp9b6SnAZ tEdOCX6SWm+D/4n8rwgcEgH1ocfKJ0UCTBz8iFR0='}, {'name': 'Received', 'value': 'by mail-vk0-f46.google.com with SMTP id s199so20113906vke.1 for <budget@yangmillstheory.com>; Wed, 30 Aug 2017 12:16:36 -0700 (PDT)'}, {'name': 'DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=gmail.com; s=20161025; h=mime-version:from:date:message-id:subject:to; bh=SEoUWjBEMpZ0/r4sgepX5xHgzXUOZcMlNJRetI5s6Is=; b=H6eaE15oF8Xp51N1bVMmjf2SzWXRtbygv2pOZnliya+9z2ykrgzDdzg8m4m9mjIdGq7J3QEI5ZCWE2F/Soc2Ql1gw0ZXNTagQdmFaUKiJwtUc+sAIbVsaUfrYTI1reRWt6+M1jCkYCTdKsTjhKyEjBG+EFh9a7ARRL9hV4e2FecYnhzfYvSVfcswns/h+J61uP3pflwo8kGxig+jhHpDFqPYdw6rH0G4GP58Xp/ReMor68Cm//+uJRMvKBZFYC8ko6rY0jvdRchIpm/Gpt1Of4Yz04xbHRmmogOM+iQER0X7ZpmN1tvh+RHm7jHzZTpqF3gdEZUClId4TnvkrrWsng=='}, {'name': 'X-Google-DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20161025; h=x-gm-message-state:mime-version:from:date:message-id:subject:to; bh=SEoUWjBEMpZ0/r4sgepX5xHgzXUOZcMlNJRetI5s6Is=; b=CEgz4tmqY71J18YTufn26E+BO4YyLCxrZhmY/uV0hKRDaa2n/nR5+kzmwyfkWHrB6L uHDfFtSleWNea5ZzD1SUNXG07JS+z9QXDmrnhaIuBKQa84/ETFUIZawQg8NSdTvdwU6N aa+i95R8O28XP3XmeNUcpSQEXutZ+flufiVx2GOCEqx1TZJ5pYXNWzijirhwO+xfhvFY RXUrcujZhmkU79AXq6FpOIyZPhpEs+Fgvw9PLZuEi+LrVc+32vuOs4R/MRoRKjR+aIqF DBe4vSOOieoql4mZO9rYm3XrXxTBFRp9WK2GBXA+fJ1sBCOyF7YauKhpT98j4MC003Ur +EMg=='}, {'name': 'X-Gm-Message-State', 'value': 'AHPjjUh1QfULxLASjeOCN49Zvb51+r8nlHA/ZQWlYneDozTzds7O6+bA G5ZZzmAPgFwSee+1DdAWJHDrXpYfEA=='}, {'name': 'X-Received', 'value': 'by 10.31.174.14 with SMTP id x14mr1559427vke.169.1504120595483; Wed, 30 Aug 2017 12:16:35 -0700 (PDT)'}, {'name': 'MIME-Version', 'value': '1.0'}, {'name': 'From', 'value': 'Victor Alvarez <v.alvarez312@gmail.com>'}, {'name': 'Date', 'value': 'Wed, 30 Aug 2017 19:16:25 +0000'}, {'name': 'Message-ID', 'value': '<CACLERZJ6+rotTdLK+-NZ8tUdczYD0MvZ_Tc2vM1iZK=K4bz2_w@mail.gmail.com>'}, {'name': 'Subject', 'value': 'Ballard market'}, {'name': 'To', 'value': '"budget@yangmillstheory.com" <budget@yangmillstheory.com>'}, {'name': 'Content-Type', 'value': 'multipart/alternative; boundary="001a1143fbdccb10190557fd5dae"'}], 'commonHeaders': {'returnPath': 'v.alvarez312@gmail.com', 'from': ['Victor Alvarez <v.alvarez312@gmail.com>'], 'date': 'Wed, 30 Aug 2017 19:16:25 +0000', 'to': ['"budget@yangmillstheory.com" <budget@yangmillstheory.com>'], 'messageId': '<CACLERZJ6+rotTdLK+-NZ8tUdczYD0MvZ_Tc2vM1iZK=K4bz2_w@mail.gmail.com>', 'subject': 'Ballard market'}}, 'receipt': {'timestamp': '2017-08-30T19:16:36.777Z', 'processingTimeMillis': 500, 'recipients': ['budget@yangmillstheory.com'], 'spamVerdict': {'status': 'PASS'}, 'virusVerdict': {'status': 'PASS'}, 'spfVerdict': {'status': 'PASS'}, 'dkimVerdict': {'status': 'PASS'}, 'action': {'type': 'Lambda', 'functionArn': 'arn:aws:lambda:us-west-2:079529114411:function:receive', 'invocationType': 'Event'}}}}]}
    handler(event)
