# budget

> Automate budget tracking

## Getting started

```
$ brew install terraform  # or brew upgrade terraform if you have it
$ terraform init          # have to do this in core/route53, core/ses as well
```

## Development

To make infrastructure changes

```
$ terraform plan
$ terraform apply # writes state to S3
```

### Lambda

Lambda processes events that are triggered when an email is sent to `budget@yangmillstheory.com`.

Here's a sample message for the email-receiver Lambda.

```python
{
  'Records': [{
    'eventSource': 'aws:ses',
    'eventVersion': '1.0',
    'ses': {
      'mail': {
        'timestamp': '2017-08-29T02:03:28.412Z',
        'source': 'v.alvarez312@gmail.com',
        'messageId': 'o1vtohr8864nq356ivm89lvoa2ot6to6n7g76j81',
        'destination': ['budget@yangmillstheory.com'],
        'headersTruncated': False,
        'headers': [{
          'name': 'Return-Path',
          'value': '<v.alvarez312@gmail.com>'
        }, {
          'name': 'Received',
          'value': 'from mail-vk0-f52.google.com (mail-vk0-f52.google.com [209.85.213.52]) by inbound-smtp.us-west-2.amazonaws.com with SMTP id o1vtohr8864nq356ivm89lvoa2ot6to6n7g76j81 for budget@yangmillstheory.com; Tue, 29 Aug 2017 02:03:28 +0000 (UTC)'
        }, {
          'name': 'X-SES-Spam-Verdict',
          'value': 'PASS'
        }, {
          'name': 'X-SES-Virus-Verdict',
          'value': 'PASS'
        }, {
          'name': 'Received-SPF',
          'value': 'pass (spfCheck: domain of _spf.google.com designates 209.85.213.52 as permitted sender) client-ip=209.85.213.52; envelope-from=v.alvarez312@gmail.com; helo=mail-vk0-f52.google.com;'
        }, {
          'name': 'Authentication-Results',
          'value': 'amazonses.com; spf=pass (spfCheck: domain of _spf.google.com designates 209.85.213.52 as permitted sender) client-ip=209.85.213.52; envelope-from=v.alvarez312@gmail.com; helo=mail-vk0-f52.google.com; dkim=pass header.i=@gmail.com;'
        }, {
          'name': 'X-SES-RECEIPT',
          'value': 'AEFBQUFBQUFBQUFGN3JLWERXK0ZueE1oU09HMHgrS0l2SHM2ZjBxNXBrNVF0SUNlazVqUExoRGNSVGQ4azhJcGhLQm5idUFBRWVJZVFpdDNUdWlnTmNmRTNESWJGSGZyNE1iVThocGFmTU5rdnBodmJXY1N3ZUFSQWp1Y1E0NGs5SjVaQnlmQkk3d3phVFRlbFVmcmxrSlZBSDJaSE5uNFBMZC9LRXFYOG1NOElxOEorVEtNNDM2UEErL1RtcW1PSHN5U3lHaXhNMlRaWVBGRmlCVjBueTFoY0U2WURHSWx2cjJYa2VPMmw2Y2tVWENDajBLMm5pY3pDTUpQMlJIUXFrQW8zYUoxV1lCdk5NNEc2OUl4aDNpcGFNd2FzbFlrVQ=='
        }, {
          'name': 'X-SES-DKIM-SIGNATURE',
          'value': 'v=1; a=rsa-sha256; q=dns/txt; c=relaxed/simple; s=hsbnp7p3ensaochzwyq5wwmceodymuwv; d=amazonses.com; t=1503972209; h=X-SES-RECEIPT:MIME-Version:From:Date:Message-ID:Subject:To:Content-Type; bh=m7NYhLHZmWnNbw0j0TiSnduVlSSUrD37JGGY1f8UExE=; b=biI5eetZ/trtqu3MPTxfKPeMzcP/PRsAE1CsrnMwQf0la6VwTjrvfNInVo6NfL/W BUNwJFzuDEVotC4rxpRg4Ib9R/pfeizFnDKTT1CGMSvBaDgBV+XMfMDgujineSTazZY eCiwXrZ9g8/owklZr1w0yBYhmlcrfLi1pVQJ+XRE='
        }, {
          'name': 'Received',
          'value': 'by mail-vk0-f52.google.com with SMTP id s199so6117407vke.1 for <budget@yangmillstheory.com>; Mon, 28 Aug 2017 19:03:28 -0700 (PDT)'
        }, {
          'name': 'DKIM-Signature',
          'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=gmail.com; s=20161025; h=mime-version:from:date:message-id:subject:to; bh=m7NYhLHZmWnNbw0j0TiSnduVlSSUrD37JGGY1f8UExE=; b=KKUCGpACqQdjlnREa8x1QDV1N99bhCM5/AUGZcaYDlRbT0fHoRkEY7ZnXgNzxfqwSTvIzrrs6JMRpMeNPulgRIKb82VECeW1YYv4gS49K2nG/ZzstKvKoE3J1Rdx62yngJIu/frhVzBOvfU2Pr433DL3OBsoA92lXu1bKa2LGB8bEsEPnm4YQ3HDNGnUNDJvezzZbLOu/xESkM7i9CgAp/SqJxxCwizt1dj+Q/lDBvHD12tTqGCwPGfnqYH3KATjGuWHEmfZU93BQyJSgC0QwLMT2tABIfxxKv4qaLceIFk66sQ+SDxGP2govPxdFQp0LJm5R8t6/8A+u/mBYlVLdw=='
        }, {
          'name': 'X-Google-DKIM-Signature',
          'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20161025; h=x-gm-message-state:mime-version:from:date:message-id:subject:to; bh=m7NYhLHZmWnNbw0j0TiSnduVlSSUrD37JGGY1f8UExE=; b=G2rvkW/GEGqTTeBpalsvE7P9T4V7JHDTW+DRGJpcTt5rlDpJH31hzDWlSlHimQOzDZ 53s1uWQmaYuGERLl74rsArOzui84VQSVudDXXOg8SvDhHo+94w4X6tNA++q4dyn8SDtz luNKOulNun58FULFLkX0IVXQBlAaiZIdXcsQppIxLHHFc/Jx1Kc83EZVQwi5A6TYBZ6U vVvkyQ6kLt6+2iR7+zkeJn1vc90w0EFxTZo9yp7/t5qKt+wqKCB50DCo3lZ2XwkKsWDm EwHh0CpVWa6ulbiR88vhfSsSiHOepAHFcQ/7hsKyVQxUqVZKlpSUBgN85cCK7iL4U9jp EdpA=='
        }, {
          'name': 'X-Gm-Message-State',
          'value': 'AHYfb5jVfDJyFHltBy1cgJZq3lXQ8zLJy6uRGu76wJQdErC+Zop5BxIO PC7IEITmOf0VEgBSHo9tBaAhrF0MKg=='
        }, {
          'name': 'X-Received',
          'value': 'by 10.31.217.193 with SMTP id q184mr1809065vkg.166.1503972207160; Mon, 28 Aug 2017 19:03:27 -0700 (PDT)'
        }, {
          'name': 'MIME-Version',
          'value': '1.0'
        }, {
          'name': 'From',
          'value': 'Victor Alvarez <v.alvarez312@gmail.com>'
        }, {
          'name': 'Date',
          'value': 'Tue, 29 Aug 2017 02:03:16 +0000'
        }, {
          'name': 'Message-ID',
          'value': '<CACLERZLLPs3w+ZSv3mi+owPo7zb=hur-DQqky9s0546oR-gS=A@mail.gmail.com>'
        }, {
          'name': 'Subject',
          'value': 'ballard market'
        }, {
          'name': 'To',
          'value': '"budget@yangmillstheory.com" <budget@yangmillstheory.com>'
        }, {
          'name': 'Content-Type',
          'value': 'multipart/alternative; boundary="94eb2c07d75e28f1af0557dad18f"'
        }],
        'commonHeaders': {
          'returnPath': 'v.alvarez312@gmail.com',
          'from': ['Victor Alvarez <v.alvarez312@gmail.com>'],
          'date': 'Tue, 29 Aug 2017 02:03:16 +0000',
          'to': ['"budget@yangmillstheory.com" <budget@yangmillstheory.com>'],
          'messageId': '<CACLERZLLPs3w+ZSv3mi+owPo7zb=hur-DQqky9s0546oR-gS=A@mail.gmail.com>',
          'subject': 'ballard market'
        }
      },
      'receipt': {
        'timestamp': '2017-08-29T02:03:28.412Z',
        'processingTimeMillis': 694,
        'recipients': ['budget@yangmillstheory.com'],
        'spamVerdict': {
          'status': 'PASS'
        },
        'virusVerdict': {
          'status': 'PASS'
        },
        'spfVerdict': {
          'status': 'PASS'
        },
        'dkimVerdict': {
          'status': 'PASS'
        },
        'action': {
          'type': 'Lambda',
          'functionArn': 'arn:aws:lambda:us-west-2:079529114411:function:email-receiver',
          'invocationType': 'Event'
        }
      }
    }
  }]
}
```


## Monitoring

* [CloudWatch logs](https://us-west-2.console.aws.amazon.com/cloudwatch/home?region=us-west-2#logStream:group=/aws/lambda/email-receiver;streamFilter=typeLogStreamPrefix)
