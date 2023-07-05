To test the application please do the following steps, as the AWS session as per the learner lab has 4 hours.

1. Replace the values of the keys with your own values in the 'aws_cred' file. 
This file contains the following information: 

[default]
aws_access_key_id=<access key id>
aws_secret_access_key=<aws secret key id>
aws_session_token=<aws session token>
VPCSecurityGroup=Security Group ID (starts with sg-****). Make sure the HTTPS, HTTP, MySQL and SSH port are enabled for Inbound.
ImageId=(Ubuntu Image ID)
image_username=<username> (By default, its Ubuntu)
region_name=<region>
KeyName=<name of key>
SecurityGroups=<Security Group Name>
lambda_endpoint=<endpoint of lambda>
function_name_lambda=<function route>
pem_file_name=<pem file of key-pair>

2. In order to test the lambda function you need to paste the code in riskanalysis/lambda_calculate_risk.py and paste in your designated endpoint and function.

3. The GitHub code which was used for AWS EC2 is also given in the riskanalysis/risk_analysis.py for checking. No need to copy/paste this file.

4. Install necessary libraries as per the 'requirements.txt' file in the environment.

5. Navigate to directory and run 'python3 index.py'

6. To deploy:

gcloud init
gcloud app deploy

Sometimes after deploying the error - 500 Internal Server Error: The server encountered an internal error and was unable to complete your request. Either the server is overloaded or there is an error in the application.

This is due to the limitations of the GAE, simply click the endpoint link again.
