import boto3
import os
import logging
import sys
import email
from collections import namedtuple
from datetime import datetime, timezone
from multiprocessing.dummy import Pool as ThreadPool
from botocore.vendored import requests


SpreadSheetRow = namedtuple(
    'SpreadSheetRow',
    ['who', 'when', 'what', 'price']
)


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
SNS = boto3.client('sns')
S3  = boto3.client('s3')
thread_pool = ThreadPool(8)


def _get_google_api_key():
    api_key = S3.get_object(
        Bucket=os.getenv('api_key_s3_bucket'),
        Key=os.getenv('api_key_s3_key')
    )
    api_key = api_key['Body']
    api_key = api_key.read()
    api_key = str(api_key)
    return api_key


api_key = _get_google_api_key()


def _is_clean(record):
    receipt_dict  = _get_receipt_dict(record)
    keys_to_check = {
        '{}Verdict'.format(key_prefix)
        for key_prefix in {'spf', 'virus', 'spam'}
    }
    for key in keys_to_check:
        if receipt_dict[key]['status'] != 'PASS':
            return False
    return True


def _get_receipt_dict(record):
    return record['ses']['receipt']


def _get_headers(record):
    return record['ses']['mail']['headers']


def _get_header_value(record, header_name):
    assert isinstance(header_name, str)
    for header_dict in _get_headers(record):
        if header_dict['name'].lower() == header_name.lower():
            return header_dict['value']
    raise ValueError('Found no header with name {}'.format(header_name))


def _get_message_id(record):
    return record['ses']['mail']['messageId']


def _to_local_format(utc_timestamp):
    dt = datetime.strptime(utc_timestamp, '%a, %d %b %Y %I:%M:%S %z')
    dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(tz=None)
    return dt.strftime('%b %d, %Y %I:%M:%S %p')

def _get_email_bytes(record):
    message_id = _get_message_id(record)
    bucket = os.getenv('email_bucket')
    prefix = os.getenv('email_prefix')
    s3_key = '{}/{}'.format(prefix, message_id)
    logger.info(
        'Getting email from bucket {} with key {}'.format(bucket, s3_key)
    )
    s3_obj = S3.get_object(Bucket=bucket, Key=s3_key)
    s3_obj = s3_obj['Body']
    return s3_obj.read()

def _get_spreadsheet_rows(record):
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
    return SpreadSheetRow(
        message['From'], _to_local_format(message['Date']), message['Subject'], price)


def handler(event, *args):
    # logger.info('Received event: {}'.format(event))
    logger.info('Got API key: {}'.format(api_key))
    records = [
        record for record in event['Records']
        if _is_clean(record)
    ]
    rows = thread_pool.map(_get_spreadsheet_rows, records)
    logger.info('Got rows {}'.format(rows))
    # _update_budget(record)
    # _notify_update(record)
    logger.info('Processed event.')


if __name__ == '__main__':
    event = {'Records': [{'eventSource': 'aws:ses', 'eventVersion': '1.0', 'ses': {'mail': {'timestamp': '2017-08-29T04:12:29.692Z', 'source': 'v.alvarez312@gmail.com', 'messageId': 'hu2fft9k1k0scv9l0iaag5qteqbvallded5djpo1', 'destination': ['budget@yangmillstheory.com'], 'headersTruncated': False, 'headers': [{'name': 'Return-Path', 'value': '<v.alvarez312@gmail.com>'}, {'name': 'Received', 'value': 'from mail-ua0-f181.google.com (mail-ua0-f181.google.com [209.85.217.181]) by inbound-smtp.us-west-2.amazonaws.com with SMTP id hu2fft9k1k0scv9l0iaag5qteqbvallded5djpo1 for budget@yangmillstheory.com; Tue, 29 Aug 2017 04:12:29 +0000 (UTC)'}, {'name': 'X-SES-Spam-Verdict', 'value': 'PASS'}, {'name': 'X-SES-Virus-Verdict', 'value': 'PASS'}, {'name': 'Received-SPF', 'value': 'pass (spfCheck: domain of _spf.google.com designates 209.85.217.181 as permitted sender) client-ip=209.85.217.181; envelope-from=v.alvarez312@gmail.com; helo=mail-ua0-f181.google.com;'}, {'name': 'Authentication-Results', 'value': 'amazonses.com; spf=pass (spfCheck: domain of _spf.google.com designates 209.85.217.181 as permitted sender) client-ip=209.85.217.181; envelope-from=v.alvarez312@gmail.com; helo=mail-ua0-f181.google.com; dkim=pass header.i=@gmail.com;'}, {'name': 'X-SES-RECEIPT', 'value': 'AEFBQUFBQUFBQUFHOC9oWlhFODZLRVZGRGxycm03eXVsYmhnZzZqeXlkQkwwT0FSMUNqeU0yNDFqczExMktWRGkxSmhOMU1teVpHcTUvdEU5Y3hnU2dlRllNUEJDZlVmNFBhTGMyVHdiM1U0bldiTkV1SGw4L0htZ2IrdWo4WEpua2dtam1TdFg2QWl3T0RXWGtBUEx3V3h1bzVDdDBIRWk5Ly9ldENJY0l2TlRSNVJQR1h0STUybEdBelVKSVF1UXhRaXE2VTlsSGEwMytVaEZlbG9JaUxnT2R4RDlDcVdEUzFQR2YyY3ppanFzbE8xOFV4aE4raHFkVDNnKzlDOWl0c21TVGQyOUxiRXBaUVRMY3JZY2Q3dCtUSElsQ1FhMg=='}, {'name': 'X-SES-DKIM-SIGNATURE', 'value': 'v=1; a=rsa-sha256; q=dns/txt; c=relaxed/simple; s=hsbnp7p3ensaochzwyq5wwmceodymuwv; d=amazonses.com; t=1503979949; h=X-SES-RECEIPT:MIME-Version:From:Date:Message-ID:Subject:To:Content-Type; bh=IvHVPBJPb0Y+ZYyvsP9okyEBqozhkW5dniNHkL4CuG8=; b=Unvj81u/tktnETNVEkxiL59q0HPLxtmOzKGbs08v4MaCx3BFAHLdzLOumxfABeZ3 6IFWmORL1cNcSpLex4nAz/Kep6Ef8RWUI1Pmh6iqcjwrfVXe7dgACcd+LdUNacJc2T7 qy68RbeqnvjExOY+xi8ys08RqlNWSy/oUcHl8w+A='}, {'name': 'Received', 'value': 'by mail-ua0-f181.google.com with SMTP id 104so7081516uas.1 for <budget@yangmillstheory.com>; Mon, 28 Aug 2017 21:12:29 -0700 (PDT)'}, {'name': 'DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=gmail.com; s=20161025; h=mime-version:from:date:message-id:subject:to; bh=IvHVPBJPb0Y+ZYyvsP9okyEBqozhkW5dniNHkL4CuG8=; b=SRnvauSW2E/POs9tfHf4yfVzGp5jEi0vfhIkJqMO4MqY8woWeOIFclWubT50eX/vrUGRLr7n5l712Jutaczaa+0JEpRpIGRy8hcu61LQB0V+kgmq4nrzzYQY53doQ7p+pdkhbRqmSlftVyI5P2BF1brf9eYiW7+CebmDX32uo39eiQVlWkjWGQiVuZArY2uAQC+3nYuh2Tds1ESUC+aIGNYBNexFj5foENsumwvwaHWexDWiULZdh6W6+7Yfsn3vzREWmR75bAsOiIqDTyU0+k/iSCsMVbwsHYJgltZv7jBL/zV9g1WEJ2BCIa+DrJ2qOfCeJO8cP98lgE9Rd4qrBQ=='}, {'name': 'X-Google-DKIM-Signature', 'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20161025; h=x-gm-message-state:mime-version:from:date:message-id:subject:to; bh=IvHVPBJPb0Y+ZYyvsP9okyEBqozhkW5dniNHkL4CuG8=; b=A1DNyl0mcO2k29STRTlz26P8lMGiu05wfhr7aXI6Buoy6i1N6DOn07Hn6uKFD+/Shk 1TAOzFQ5ZkTyDYdjS+1o03YrKTtBfbEpBze6auuj5RtcKhDE3kmVmuL3eC0ohfOLn8X0 qs0EVfTFuoqm/KpVJGg5waZna+KWvZa8FT4/Hdx3+733wxi+dkzm2CkfNsFqgUVvMh9K RpUlVMtHeJ0U3hrJKHHDb5EHc5E6oYcu84lADrUu9UlebhxGCO+K1XFfFGMtNRKucQ1c kuNqxb3szsAAChO9V8HlM6aiBp4SarglRUEwOxe2vUdVAA66VbNWv3uIjrTEeg7biKiA k0SA=='}, {'name': 'X-Gm-Message-State', 'value': 'AHYfb5hDxhVGRRAYGxUXI+l2Rlm4Scbl5Y01woYW1msh2ZuxVFnyof/r cnLf0mjO2pxpqIKoWH83TTM/HMZ8xg=='}, {'name': 'X-Received', 'value': 'by 10.176.91.20 with SMTP id u20mr1929838uae.184.1503979948384; Mon, 28 Aug 2017 21:12:28 -0700 (PDT)'}, {'name': 'MIME-Version', 'value': '1.0'}, {'name': 'From', 'value': 'Victor Alvarez <v.alvarez312@gmail.com>'}, {'name': 'Date', 'value': 'Tue, 29 Aug 2017 04:12:17 +0000'}, {'name': 'Message-ID', 'value': '<CACLERZJp6Y05GbC-xEmga9_CzOxKOo7fjdjf2eQ-xOvozA7iDw@mail.gmail.com>'}, {'name': 'Subject', 'value': 'ballard market'}, {'name': 'To', 'value': '"budget@yangmillstheory.com" <budget@yangmillstheory.com>'}, {'name': 'Content-Type', 'value': 'multipart/alternative; boundary="f403045f8b5692a6f30557dc9e23"'}], 'commonHeaders': {'returnPath': 'v.alvarez312@gmail.com', 'from': ['Victor Alvarez <v.alvarez312@gmail.com>'], 'date': 'Tue, 29 Aug 2017 04:12:17 +0000', 'to': ['"budget@yangmillstheory.com" <budget@yangmillstheory.com>'], 'messageId': '<CACLERZJp6Y05GbC-xEmga9_CzOxKOo7fjdjf2eQ-xOvozA7iDw@mail.gmail.com>', 'subject': 'ballard market'}}, 'receipt': {'timestamp': '2017-08-29T04:12:29.692Z', 'processingTimeMillis': 410, 'recipients': ['budget@yangmillstheory.com'], 'spamVerdict': {'status': 'PASS'}, 'virusVerdict': {'status': 'PASS'}, 'spfVerdict': {'status': 'PASS'}, 'dkimVerdict': {'status': 'PASS'}, 'action': {'type': 'Lambda', 'functionArn': 'arn:aws:lambda:us-west-2:079529114411:function:email-receiver', 'invocationType': 'Event'}}}}]}
    handler(event)
