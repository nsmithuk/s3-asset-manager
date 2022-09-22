import os

import boto3
import boto3.session
from boto3 import Session
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session


def get_s3_client(logger):
    if 'AWS_ROLE' in os.environ:

        def _refresh():
            params = {
                "RoleArn": os.environ['AWS_ROLE'],
                "DurationSeconds": 60 * 20,
                "RoleSessionName": "s3-asset-manager",
            }
            response = boto3.client('sts').assume_role(**params).get("Credentials")
            credentials = {
                "access_key": response.get("AccessKeyId"),
                "secret_key": response.get("SecretAccessKey"),
                "token": response.get("SessionToken"),
                "expiry_time": response.get("Expiration").isoformat(),
            }
            return credentials

        session_credentials = RefreshableCredentials.create_from_metadata(
            metadata=_refresh(),
            refresh_using=_refresh,
            method="sts-assume-role",
        )

        session = get_session()
        session._credentials = session_credentials
        autorefresh_session = Session(botocore_session=session)

        logger.info(f"Accessing S3 using assumed role: {os.environ['AWS_ROLE']}")
        return autorefresh_session.client('s3')
    else:
        logger.info(f"Accessing S3 using credentials in environment variables")
        return boto3.client('s3')
