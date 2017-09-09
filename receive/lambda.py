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
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(threadName)s %(module)s:%(lineno)s %(message)s'))
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
    dt_formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S',
    ]
    dt = None
    for dt_format in dt_formats:
        try:
            dt = datetime.strptime(utc_timestamp, dt_format)
        except Exception as e:
            logger.info("Couldn't parse {} with format {}".format(utc_timestamp, dt_format))
        else:
            break
    if not dt:
        logger.info("Couldn't format {} at all; returning it.".format(utc_timestamp))
        return utc_timestamp
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
            price = None
            logger.info("Couldn't get price: {}".format(e))
        else:
            break
    if not price:
        raise Exception('No price found for message_id {}'.format(_get_message_id(record)))
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
        return ', '.join([
            csv_row.who,
            _to_local_format(csv_row.when),
            csv_row.what,
            '${:.2f}'.format(csv_row.price),
        ])

    message_lines = list(map(get_message_line, csv_rows))
    message_lines.append('Total spend for period is now: ${:.2f}'.format(period_spend))
    delta = MAX_PERIOD_SPEND - period_spend
    if delta < 0:
        message_lines.append('You went ${:.2f} over budget!'.format(-delta))
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
    if not os.getenv('dry_run'):
        _commit_csv()
    period_spend = _get_period_spend()
    _notify_update(csv_rows, period_spend)
    logger.info('Processed event.')


if __name__ == '__main__':
    event = {'Records': [{'eventSource': 'aws:ses', 'eventVersion': '1.0', 'ses': {'mail': {'timestamp': '2017-09-02T04:43:30.756Z', 'source': 'v.alvarez312@gmail.com', 'messageId': '0pg0k9ut54o0ar4305111hucc20u6b01mmq2e681', 'destination': ['budget@yangmillstheory.com'], 'headersTruncated': False, 'headers': [{'name': 'Return-Path', 'value': '<v.alvarez312@gmail.com>'}, {'name': 'Received', 'value': 'from mail-vk0-f48.google.com (mail-vk0-f48.google.com [209.85.213.48]) by inbound-smtp.us-west-2.amazonaws.com with SMTP id 0pg0k9ut54o0ar4305111hucc20u6b01mmq2e681 for budget@yangmillstheory.com; Sat, 02 Sep 2017 04:43:30 +0000 (UTC)'}, {'name': 'X-SES-Spam-Verdict', 'value': 'PASS'}, {'name': 'X-SES-Virus-Verdict', 'value': 'PASS'}, {'name': 'Received-SPF', 'value': 'pass (spfCheck: domain of _spf.google.com designates 209.85.213.48 as permitted sender) client-ip=209.85.213.48; envelope-from=v.alvarez312@gmail.com; helo=mail-vk0-f48.google.com;'}, {'name': 'Authentication-Results', 'value': 'amazonses.com; spf=pass (spfCheck: domain of _spf.google.com designates 209.85.213.48 as permitted sender) client-ip=209.85.213.48; envelope-from=v.alvarez312@gmail.com; helo=mail-vk0-f48.google.com; dkim=pass header.i=@gmail.com;'}, {'name': 'X-SES-RECEIPT', 'value': 'AEFBQUFBQUFBQUFHVWVmUzM0NW82azV5d3ozUm92UGtIVGZEaG1EMTVKejRtazJtTEV2TldaMGd6dTlIMG93Y05mUjRsVFFsTFdXbnNSNndXQjVDL1puWVZLdWZYUm5sc0pVTFpZQVVla1hHVFYvU2FUcjF0L3Y0em1FQlpFcUwvTDVtTTBabk4raktuNktaa1N0Q0FBNXNWbmUySkhnb0VmcW1XQzNtdGExR05jYzhJZ2hpZlNzbTgvR0ZsQ0paaVd2RTVNVUl4RXlTVktYRzFYY21YZzBSaS83NGtEa0VLUDVORzM1cVNUTnNjcjA4ZVQ4L3lFNGpiODdQV0sxTlMxaGQ2aDJwbVNiNzRJUzRwUE5XZmVOZ25lNkFxOXdBeg=='}, {'name': 'X-SES-DKIM-SIGNATURE', 'value': 'v=1; a=rsa-sha256; q=dns/txt; c=relaxed/simple; s=hsbnp7p3ensaochzwyq5wwmceodymuwv; d=amazonses.com; t=1504327411; h=X-SES-RECEIPT:MIME-Version:From:Date:Message-ID:Subject:To:Content-Type; bh=7aM3OTCcW1914AFXnCAiQ7pW9txotzS8XxJNMX3NHW0=; b=CbDtQ3ji6CnA/9uvvbs+mP+fhx7G0UgvFxEci53TnEszJmPogr3J5GKWCSDyeAgZ KnKniKL75kiI/64mXRmmUkYOrQ8WnA7ZhBqcweWIgByb8RIHuR8n6Mxzs7gnOp2Hvkj 0sZmVsfSj6LoVnNUX9cDxigGImvDx9qhNxKZifzA='}, {'name': 'Received', 'value': 'by mail-vk0-f48.google.com with SMTP id q189so5046750vke.4 for <budget@yangmillstheory.com>; Fri, 01 Sep 2017 21:43:30 -0700 (PDT)'}, {'name': 'DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=gmail.com; s=20161025; h=mime-version:from:date:message-id:subject:to; bh=7aM3OTCcW1914AFXnCAiQ7pW9txotzS8XxJNMX3NHW0=; b=slpcolxtR+yEN7JERwZImbwBhjQT8uJA6KmFpWHhi26aPXphHoJXoKTL4Ac+wCBzJvN/BA8SSVCZFe+ZWXNW91ujZT5f0zSHXk55v5IHIjX7ntSCXIEmswqvQ2/ZBlfMSYmkMMo0TCh4Zw4gYYI8mMM6zR77ODkschVG8BT3i+cq49KBz8NmcPqcll70fDyD/ms1RNg/k3rMrcF9fZPopJSRM/jG5BVpSpbwHi8AJ0OCteccogF8QTMXXt48ALaFdajNc+pxw5EEuTPKB0faWxpR6mEelIPwOBFyxypTN2NavWDiqyaxOdnl6LH3y9vY8+K3i+0cYzTtoxNWZDHwmA=='}, {'name': 'X-Google-DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20161025; h=x-gm-message-state:mime-version:from:date:message-id:subject:to; bh=7aM3OTCcW1914AFXnCAiQ7pW9txotzS8XxJNMX3NHW0=; b=mWgcqyleYM6PkV/M+5rSAbq3RmNDDvjhRvo6to1AYzbjt4WMpyVF6ap20o3TqY9sMS UouvARhd/yA5ZjnMNbAxuRbwMdbyEX4cFW9w7n0GL8YimstMzNQSA6SsUlvaKl2UyBIR Lt0+ZPG/daGuolqdzPPNeZNoViX6xg+rya6LhnekwG/qCoeA3EkATM15gSIhtJksDBF5 nVEiE/HYrF3XjPAtOqe79iIzLm19Bciz0Pbh6bn4YjHDw6Zd3Uq3boEP5eT641ZDKodI OxmwY0iW9zFxQbwFJvL64z7bUN9sFVh+RKAL65b3gdIPGhf0X/XHD9rGQ89B8ljZFWQB ZCZw=='}, {'name': 'X-Gm-Message-State', 'value': 'AHPjjUgrTxnke09WU3p6BdYhLUJ9Mq+Omu7LWMZkU/bHNtC5vR/gRP5N QpY44hspcKct8/hz1yLmHe1S0Z6ppQ=='}, {'name': 'X-Google-Smtp-Source', 'value': 'ADKCNb7Xv4C6Q4oQaiDKxGsEJbHP9ghwOU78+f+e9pfgAgIrPEk6/+nnKWydOUZGITcf/enEP7LGCeEhQ0+McrsZvmI='}, {'name': 'X-Received', 'value': 'by 10.31.92.151 with SMTP id q145mr2598469vkb.39.1504327409477; Fri, 01 Sep 2017 21:43:29 -0700 (PDT)'}, {'name': 'MIME-Version', 'value': '1.0'}, {'name': 'From', 'value': 'Victor Alvarez <v.alvarez312@gmail.com>'}, {'name': 'Date', 'value': 'Sat, 02 Sep 2017 04:43:19 +0000'}, {'name': 'Message-ID', 'value': '<CACLERZ+Ri-7hUNG0KwMbmK=sRmn7zJPJ=YVJ1_Yr3YU1Z0QLZg@mail.gmail.com>'}, {'name': 'Subject', 'value': 'Juice'}, {'name': 'To', 'value': 'budget@yangmillstheory.com'}, {'name': 'Content-Type', 'value': 'multipart/alternative; boundary="001a114e578ede2e6605582d84e5"'}], 'commonHeaders': {'returnPath': 'v.alvarez312@gmail.com', 'from': ['Victor Alvarez <v.alvarez312@gmail.com>'], 'date': 'Sat, 02 Sep 2017 04:43:19 +0000', 'to': ['budget@yangmillstheory.com'], 'messageId': '<CACLERZ+Ri-7hUNG0KwMbmK=sRmn7zJPJ=YVJ1_Yr3YU1Z0QLZg@mail.gmail.com>', 'subject': 'Juice'}}, 'receipt': {'timestamp': '2017-09-02T04:43:30.756Z', 'processingTimeMillis': 943, 'recipients': ['budget@yangmillstheory.com'], 'spamVerdict': {'status': 'PASS'}, 'virusVerdict': {'status': 'PASS'}, 'spfVerdict': {'status': 'PASS'}, 'dkimVerdict': {'status': 'PASS'}, 'action': {'type': 'Lambda', 'functionArn': 'arn:aws:lambda:us-west-2:079529114411:function:receive', 'invocationType': 'Event'}}}}]}
    handler(event)
