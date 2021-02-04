"""Speech to text recognition with writing to postgres database"""

import logging
import os
import argparse
import sys
import uuid
from datetime import datetime
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from tinkoff_voicekit_client import ClientSTT
from config import API_KEY, SECRET_KEY, DBNAME, USER, PASSWORD, HOST, PORT


def speech_to_description(description, filename):
    """Speech to text with Tinkoff API
    https://github.com/TinkoffCreditSystems/voicekit_client_python"""

    audio_config = {
        "encoding": "LINEAR16",
        "sample_rate_hertz": 8000,
        "num_channels": 1
    }

    client = ClientSTT(API_KEY, SECRET_KEY)
    response = client.recognize(filename, audio_config)

    description['uid'] = str(uuid.uuid4())
    description['duration'] = \
        '{:.3f}s'.format(float(response[0]['end_time'][:-1]) -
                         float(response[0]['start_time'][:-1]))
    description['text'] = response[0]['alternatives'][0]['transcript']


def define_status(description, stage):
    """
    Determining whether the subscriber is human and whether he is
    ready to continue the conversation

    stage = 0: check person or answering machine
    stage = 1: check the person is ready to continue the conversation
    """
    status = None

    if description['text'] == '-':
        return status

    negative_words = ["нет", "неудобно"]
    positive_words = ["да", "конечно", "удобно"]

    if "автоответчик" in description['text']:
        status = 0
        description['status'] = "автоответчик"
    else:
        status = 1
        description['status'] = "человек"

    if stage and status:
        for word in description['text'].split():
            if word in negative_words:
                status = 0
                description['status'] = "отрицательно"
            elif word in positive_words:
                status = 1
                description['status'] = "положительно"

    return status


def write_log(description):
    """Logging calls information"""

    logger = logging.getLogger('dev')
    logger.setLevel(logging.INFO)

    logger.addHandler(logging.FileHandler('recognition.log'))
    description['dtime'] = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info(description['dtime'] + ', ' +
                description['uid'] + ', ' +
                description['status'] + ', ' +
                description['phone'] + ', ' +
                description['duration'] + ', ' +
                description['text'])


def write_db(description):
    """Write calls information to postgres database"""

    with psycopg2.connect(dbname=DBNAME,
                          user=USER,
                          password=PASSWORD,
                          host=HOST,
                          port=PORT) as conn:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cursor:

            cursor.execute(
                "INSERT INTO {table} (dtime, uid, status, phone, duration, \
                text) VALUES ('{dtime}', '{uid}', '{status}', '{phone}', \
                '{duration}', '{text}');".format(
                                            table='"Calls"',
                                            dtime=description['dtime'],
                                            uid=description['uid'],
                                            status=description['status'],
                                            phone=description['phone'],
                                            duration=description['duration'],
                                            text=description['text']
                                        )
            )


def create_parser():
    """Command line parser

    arguments:
        filename: .wav file with conversation recording
        phone: phone number
        --to-db: write to database if 1
        --stage: check sentiment of conversation if 1
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('filename', type=str)
    parser.add_argument('phone', nargs='?', type=str, default='-')
    parser.add_argument('--to-db', nargs='?', type=int, default=0,
                        choices=[0, 1])
    parser.add_argument('--stage', nargs='?', type=int, default=0,
                        choices=[0, 1])
    return parser


def run_recognition():
    """Recognition wrapper"""

    error_logger = logging.getLogger('error')
    error_logger.addHandler(logging.FileHandler('errors.log'))

    parser = create_parser()
    args = parser.parse_args(sys.argv[1:])

    description = {
            'dtime': '-',
            'uid': '-',
            'status': 'не определено',
            'phone': args.phone,
            'duration': '-',
            'text': '-'
    }

    try:
        speech_to_description(description, args.filename)
    except Exception as exc:
        error_logger.error('RecognitionError: %s', exc)
    else:
        status = define_status(description, args.is_human)

        write_log(description)

        if args.to_db:
            try:
                write_db(description)
            except Exception as exc:
                error_logger.error('DatabaseError: %s', exc)

        try:
            os.remove(args.filename)
        except Exception as exc:
            error_logger.error('RemoveError: %s', exc)

        return status


if __name__ == '__main__':
    run_recognition()
