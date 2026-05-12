import boto3
import json
import os
from botocore.exceptions import ClientError

def get_secret():
    """Fetch VF_Accio_Sandbox_Cred from AWS Secrets Manager."""
    secret_name = "VF_Accio_Sandbox_Cred"
    region_name = "us-east-1" 

    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        resp = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        print(f"Error retrieving secret from AWS: {e}")
        raise e

    creds = json.loads(resp["SecretString"])
    return creds.get("Username"), creds.get("Password"), creds.get("Account")

def run_application():
    try:
        # 1. Fetch credentials dynamically from AWS
        username, password, account = get_secret()
        
        # 2. Inject into Environment Variables (In-Memory only)
        os.environ["USER_ID"] = username
        os.environ["USER_PWD"] = password
        os.environ["ACC_ID"] = account
        
        print("Successfully injected credentials into environment variables.")
        
        # 3. Now, other parts of your code can access these via os.getenv()
        # Example:
        # my_user = os.getenv("USER_ID")
        # print(f"Working with user: {my_user}")
        
    except Exception as e:
        print(f"Failed to initialize application: {e}")

if __name__ == "__main__":
    run_application()