import json
import sys
import unittest
from datetime import datetime

import botocore.config
from botocore.exceptions import ClientError

from localstack.constants import TEST_AWS_ACCOUNT_ID
from localstack.utils.aws import aws_stack
from localstack.utils.common import short_uid

RESOURCE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": "arn:aws:iam::%s:root" % TEST_AWS_ACCOUNT_ID},
            "Action": "secretsmanager:GetSecretValue",
            "Resource": "*",
        }
    ],
}


class SecretsManagerTest(unittest.TestCase):
    def setUp(self):
        self.secretsmanager_client = aws_stack.create_external_boto_client("secretsmanager")

    def test_create_and_update_secret(self):
        secret_name = "s-%s" % short_uid()
        rs = self.secretsmanager_client.create_secret(
            Name=secret_name,
            SecretString="my_secret",
            Description="testing creation of secrets",
        )
        secret_arn = rs["ARN"]

        self.assertEqual(6, len(secret_arn.rpartition("-")[2]))

        rs = self.secretsmanager_client.get_secret_value(SecretId=secret_name)
        self.assertEqual(secret_name, rs["Name"])
        self.assertEqual("my_secret", rs["SecretString"])
        self.assertEqual(secret_arn, rs["ARN"])
        self.assertTrue(isinstance(rs["CreatedDate"], datetime))

        rs = self.secretsmanager_client.get_secret_value(SecretId=secret_arn)
        self.assertEqual(secret_name, rs["Name"])
        self.assertEqual("my_secret", rs["SecretString"])
        self.assertEqual(secret_arn, rs["ARN"])

        rs = self.secretsmanager_client.get_secret_value(SecretId=secret_arn[: len(secret_arn) - 6])
        self.assertEqual(secret_name, rs["Name"])
        self.assertEqual("my_secret", rs["SecretString"])
        self.assertEqual(secret_arn, rs["ARN"])

        rs = self.secretsmanager_client.get_secret_value(SecretId=secret_arn[: len(secret_arn) - 7])
        self.assertEqual(secret_name, rs["Name"])
        self.assertEqual("my_secret", rs["SecretString"])
        self.assertEqual(secret_arn, rs["ARN"])

        self.secretsmanager_client.put_secret_value(SecretId=secret_name, SecretString="new_secret")

        rs = self.secretsmanager_client.get_secret_value(SecretId=secret_name)
        self.assertEqual(secret_name, rs["Name"])
        self.assertEqual("new_secret", rs["SecretString"])

        # update secret by ARN
        rs = self.secretsmanager_client.update_secret(
            SecretId=secret_arn, KmsKeyId="test123", Description="d1"
        )
        self.assertEqual(200, rs["ResponseMetadata"]["HTTPStatusCode"])
        self.assertEqual(secret_arn, rs["ARN"])

        # clean up
        self.secretsmanager_client.delete_secret(
            SecretId=secret_name, ForceDeleteWithoutRecovery=True
        )

    def test_call_lists_secrets_multiple_time(self):
        secret_name = "s-%s" % short_uid()
        self.secretsmanager_client.create_secret(
            Name=secret_name,
            SecretString="my_secret",
            Description="testing creation of secrets",
        )

        # call list_secrets multiple times
        for i in range(3):
            rs = self.secretsmanager_client.list_secrets()
            secrets = [secret for secret in rs["SecretList"] if secret["Name"] == secret_name]
            self.assertEqual(1, len(secrets))

        # clean up
        self.secretsmanager_client.delete_secret(
            SecretId=secret_name, ForceDeleteWithoutRecovery=True
        )

    def test_create_multi_secrets(self):
        secret_names = [short_uid(), short_uid(), short_uid()]
        arns = []
        for secret_name in secret_names:
            rs = self.secretsmanager_client.create_secret(
                Name=secret_name,
                SecretString="my_secret_{}".format(secret_name),
                Description="testing creation of secrets",
            )
            arns.append(rs["ARN"])

        rs = self.secretsmanager_client.list_secrets()
        secrets = {
            secret["Name"]: secret["ARN"]
            for secret in rs["SecretList"]
            if secret["Name"] in secret_names
        }

        self.assertEqual(len(secret_names), len(secrets.keys()))
        for arn in arns:
            self.assertIn(arn, secrets.values())

        # clean up
        for secret_name in secret_names:
            self.secretsmanager_client.delete_secret(
                SecretId=secret_name, ForceDeleteWithoutRecovery=True
            )

    def test_get_random_exclude_characters_and_symbols(self):
        random_password = self.secretsmanager_client.get_random_password(
            PasswordLength=120, ExcludeCharacters="xyzDje@?!."
        )

        self.assertEqual(120, len(random_password["RandomPassword"]))
        self.assertTrue(all(c not in "xyzDje@?!." for c in random_password["RandomPassword"]))

    def test_resource_policy(self):
        secret_name = "s-%s" % short_uid()

        self.secretsmanager_client.create_secret(
            Name=secret_name,
            SecretString="my_secret",
            Description="testing creation of secrets",
        )

        self.secretsmanager_client.put_resource_policy(
            SecretId=secret_name, ResourcePolicy=json.dumps(RESOURCE_POLICY)
        )

        rs = self.secretsmanager_client.get_resource_policy(SecretId=secret_name)

        policy = json.loads(rs["ResourcePolicy"])

        self.assertEqual(RESOURCE_POLICY["Version"], policy["Version"])
        self.assertEqual(RESOURCE_POLICY["Statement"], policy["Statement"])

        rs = self.secretsmanager_client.delete_resource_policy(SecretId=secret_name)
        self.assertEqual(200, rs["ResponseMetadata"]["HTTPStatusCode"])

        # clean up
        self.secretsmanager_client.delete_secret(
            SecretId=secret_name, ForceDeleteWithoutRecovery=True
        )

    def create_and_get_secret(self, boto_sm_client):
        secret_name: str = "s-%s" % short_uid()
        secret_string: str = str(short_uid())

        rs_create: dict = boto_sm_client.create_secret(Name=secret_name, SecretString=secret_string)
        self.assertEqual(200, rs_create['ResponseMetadata']['HTTPStatusCode'])
        self.assertEqual(secret_name, rs_create["Name"])

        rs_get: dict = boto_sm_client.get_secret_value(SecretId=secret_name)
        self.assertEqual(secret_name, rs_get['Name'])
        self.assertEqual(secret_string, rs_get["SecretString"])
        self.assertEqual(rs_create['ARN'], rs_get['ARN'])
        self.assertTrue(isinstance(rs_get['CreatedDate'], datetime))

    def test_boto3_client_no_region_create_and_get_secret(self):
        import boto3
        secretsmanager_client_nr = boto3.client(
            'secretsmanager',
            endpoint_url=aws_stack.get_local_service_url('secretsmanager'),
            config=botocore.config.Config(retries=dict(max_attempts=1))
        )
        try:
            self.create_and_get_secret(secretsmanager_client_nr)
        except ClientError as ce:
            self.assertNotEqual(500, int(ce.response['Error']['Code']))

    def test_boto3_client_null_region_create_and_get_secret(self):
        import boto3
        secretsmanager_client_nr = boto3.client(
            'secretsmanager',
            region_name=None,
            endpoint_url=aws_stack.get_local_service_url('secretsmanager'),
            config=botocore.config.Config(retries=dict(max_attempts=1))
        )
        try:
            self.create_and_get_secret(secretsmanager_client_nr)
        except ClientError as ce:
            self.assertNotEqual(500, int(ce.response['Error']['Code']))

    def test_boto3_client_with_region_create_and_get_secret(self):
        import boto3
        secretsmanager_client_nr = boto3.client(
            'secretsmanager',
            region_name=aws_stack.get_region(),
            endpoint_url=aws_stack.get_local_service_url('secretsmanager'),
            config=botocore.config.Config(retries=dict(max_attempts=1))
        )
        try:
            self.create_and_get_secret(secretsmanager_client_nr)
        except ClientError as ce:
            self.assertNotEqual(500, int(ce.response['Error']['Code']))

    def test_boto3_client_region_scenario1(self):
        # Failing requests should not prevent future valid requests to succeed.
        try:
            self.test_boto3_client_no_region_create_and_get_secret()
        except AssertionError as ae:
            # Fail quietly: scenario tests the following statement.
            print(ae, file=sys.stderr)
        self.test_boto3_client_with_region_create_and_get_secret()

    def test_boto3_client_region_scenario2(self):
        # First -non-failing- requests is correctly handled, but future failing
        # requests continue failing.
        self.test_boto3_client_with_region_create_and_get_secret()
        self.test_boto3_client_no_region_create_and_get_secret()

    def test_boto3_client_region_scenario3(self):
        # First -non-failing- request is correctly handled, and all future -non-failing- request
        # following a failing request continue being handled correctly
        self.test_boto3_client_with_region_create_and_get_secret()
        try:
            self.test_boto3_client_no_region_create_and_get_secret()
        except AssertionError as ae:
            # Fail quietly: scenario tests the following statement.
            print(ae, file=sys.stderr)
        self.test_boto3_client_with_region_create_and_get_secret()
