import boto3
import cfnresponse
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    CloudFormation Custom Resource handler to set Cognito User Password.
    """
    logger.info('Received event: %s', json.dumps(event, default=str))

    try:
        if event['RequestType'] == 'Delete':
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return

        user_pool_id = event['ResourceProperties']['UserPoolId']
        username = event['ResourceProperties']['Username']
        password = event['ResourceProperties']['Password']

        cognito = boto3.client('cognito-idp')

        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=username,
            Password=password,
            Permanent=True
        )

        logger.info(f"Password set successfully for user: {username}")

        cfnresponse.send(event, context, cfnresponse.SUCCESS, {
            'Status': 'SUCCESS',
            'Username': username
        })

    except Exception as e:
        logger.error('Error setting password: %s', str(e))
        cfnresponse.send(event, context, cfnresponse.FAILED, {
            'Error': str(e)
        })
