import boto3
import csv
import os
import logging
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


BUDGET_FILE_NAME = os.environ['csv_key']
LOCAL_CSV_PATH = '/tmp/{}'.format(BUDGET_FILE_NAME)
RESET_RECIPIENTS = os.getenv('reset_recipients').split(',')
MAX_PERIOD_SPEND = float(os.getenv('max_period_spend'))


def get_logger():
    logger = logging.getLogger(__name__)
    for handler in logger.handlers:
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter('[%(levelname)s] %(module)s:%(lineno)s %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger()
sns = boto3.client('sns')
ses = boto3.client('ses')
s3 = boto3.client('s3')


def _download_csv():
    """Downloads the budget csv from S3."""
    s3.download_file(
        os.getenv('csv_bucket'), os.getenv('csv_key'), LOCAL_CSV_PATH)


def _reset_csv():
    """Overwrites the active budget with an empty budget template."""
    logger.info('Resetting budget CSV.')
    bucket = os.getenv('csv_bucket')
    s3.copy(
        {'Bucket': bucket, 'Key': os.getenv('csv_template_key')},
        Bucket=bucket,
        Key=os.getenv('csv_key')
    )
    sns.publish(
        TopicArn=os.getenv('sns_topic_arn'),
        Message='Starting new budget period. Good luck!'
    )
    logger.info('Reset budget.')


def _notify_period_spend():
    """Sums all the prices in the price column of the csv
    and sends a notification with the results.
    """
    with open(LOCAL_CSV_PATH, newline='') as f:
        prices = [float(row['price']) for row in csv.DictReader(f)]
    period_spend = sum(prices)
    logger.info('Sending summary notification.')
    message_lines = ['Budget period ending!']
    message_lines.append(
        'Total spent for this period is ${:.2f}'.format(period_spend))
    delta = MAX_PERIOD_SPEND - period_spend
    if delta < 0:
        message_lines.append('You went ${:.2f} over budget!'.format(-delta))
    else:
        message_lines.append(
            'Made it with ${:.2f} savings. Way to go!'.format(delta))
    sns.publish(
        TopicArn=os.getenv('sns_topic_arn'),
        Message=os.linesep.join(message_lines)
    )
    logger.info('Sent summary notification.')


def _send_csv_email():
    """Sends the downloaded CSV file to a list of recipients."""
    message = MIMEMultipart()
    message['Subject'] = 'Budget Period Log'
    message['From'] = 'budget@yangmillstheory.com'
    with open(LOCAL_CSV_PATH, 'rb') as f:
        # yes, read all the bytes into memory; the file is small
        attachment = MIMEApplication(f.read())
    attachment.add_header(
        'Content-Disposition', 'attachment', filename=BUDGET_FILE_NAME)
    message.attach(attachment)
    logger.info('Sending CSV file to {}'.format(RESET_RECIPIENTS))
    ses.send_raw_email(
        Source=message['From'],
        Destinations=RESET_RECIPIENTS,
        RawMessage={
            'Data': message.as_string(),
        })
    logger.info('Email sent.')


def handler(*args):
    """Sends a summary for the current budget via SMS and email, then resets
    the template.
    """
    logger.info('Resetting budget.')
    _download_csv()
    _notify_period_spend()
    _send_csv_email()
    if not os.getenv('dry_run'):
        _reset_csv()
    logger.info('Budget reset.')


if __name__ == '__main__':
    handler()
