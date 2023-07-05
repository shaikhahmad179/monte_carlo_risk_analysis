import os
import logging
from flask import Flask, request, render_template, Response, redirect, make_response
import math
import random
import yfinance as yf
from datetime import date, timedelta, datetime
from pandas_datareader import data as pdr
import pandas as pd
import http.client
import json
import ast
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import boto3
import urllib.parse
from io import BytesIO
import requests
import base64
import boto3
import pymysql
import paramiko
import concurrent.futures
import configparser

time_to_load_data = time.time()

app = Flask(__name__)

yf.pdr_override()

today = date.today()
decadeAgo = today - timedelta(days=1095)

data = pdr.get_data_yahoo('ZM', start=decadeAgo, end=today)

data['Buy']=0
data['Sell']=0

for i in range(2, len(data)):

	body = 0.01

	       # Three Soldiers
	if (data.Close[i] - data.Open[i]) >= body and data.Close[i] > data.Close[i-1] and (data.Close[i-1] - data.Open[i-1]) >= body and data.Close[i-1] > data.Close[i-2] and (data.Close[i-2] - data.Open[i-2]) >= body:
		data.at[data.index[i], 'Buy'] = 1

       		# Three Crows
	if (data.Open[i] - data.Close[i]) >= body and data.Close[i] < data.Close[i-1] and (data.Open[i-1] - data.Close[i-1]) >= body and data.Close[i-1] < data.Close[i-2] and (data.Open[i-2] - data.Close[i-2]) >= body:
		data.at[data.index[i], 'Sell'] = 1


data = data.reset_index(drop=False)
data['Date'] = data['Date'].dt.date
data['Date'] = data['Date'].astype('str')

data_list = data.values.tolist()


# Loads the aws_cred file which contains the credentials and other information vital to run the project.
os.environ['AWS_SHARED_CREDENTIALS_FILE']='aws_cred'

config = configparser.ConfigParser()
config.read(os.environ['AWS_SHARED_CREDENTIALS_FILE'])

access_key_id = str(config.get('default', 'aws_access_key_id'))
secret_access_key = str(config.get('default', 'aws_secret_access_key'))
session_token = str(config.get('default', 'aws_session_token'))
security_group_id_db = str(config.get('default', 'VPCSecurityGroup'))
ubuntu_image_id = str(config.get('default', 'ImageId'))
ubuntu_image_username = str(config.get('default', 'image_username'))
name_of_region = str(config.get('default', 'region_name'))
name_of_key = str(config.get('default', 'KeyName'))
security_group_id_ec2 = str(config.get('default', 'SecurityGroups'))
lambda_endpoint = str(config.get('default', 'lambda_endpoint'))
function_name_lambda = str(config.get('default', 'function_name_lambda'))
pem_file_name = str(config.get('default', 'pem_file_name'))

time_to_load_data = time.time() - time_to_load_data
# --------------------------- AWS RDS Database (Audit Log) ----------------------------------------------------
# Creates the RDS DB Instance (RUN ONCE)
def create_db_instance(rds, db_parameters):

	# Create the RDS instance
	rds_instance = rds.create_db_instance(DBInstanceIdentifier = db_parameters["db_instance_identifier"], DBName= db_parameters["db_name"], MasterUsername=db_parameters["db_username"], MasterUserPassword=db_parameters["db_password"], DBInstanceClass=db_parameters["db_instance_class"], Engine=db_parameters["engine"], EngineVersion=db_parameters["engine_version"], AllocatedStorage=db_parameters["allocated_storage"], VpcSecurityGroupIds = db_parameters["VPCSecurityGroup"])

# Get Connection of RDS
def get_connection(rds, db_parameters):

	# Endpoint address for db instance
	response = rds.describe_db_instances(DBInstanceIdentifier=db_parameters["db_instance_identifier"])
	endpoint = response['DBInstances'][0]['Endpoint']['Address']
	
	# Connect to the RDS instance
	connection = pymysql.connect(
	    host = endpoint,
	    user = db_parameters["db_username"],
	    password = db_parameters["db_password"],
	    database = db_parameters["db_name"],
	    connect_timeout = 80
	)
	
	return connection


# Creates Table (RUN ONCE)
def create_table(connection, db_table_name):
	
	sql = '''CREATE TABLE ''' + db_table_name + '''(
	    	created_at VARCHAR(255),
	    	service VARCHAR(255),
	    	resources INT,
	    	minhistory INT,
	    	shots INT,
	    	profit_loss INT,
	    	transaction_type VARCHAR(255),
	    	execution_time DOUBLE,
	    	warmup_time DOUBLE,
	    	operation_cost DOUBLE,
	    	total_profit DOUBLE,
	    	total_loss DOUBLE,
	    	var95_avg DOUBLE,
	    	var99_avg DOUBLE
	    )'''
	    
	with connection.cursor() as cursor:
	    cursor.execute(sql)

	connection.commit()
	
# Inserts data to table
def insert_data(connection, form_data, db_table_name):
	
	current_timestamp = datetime.now()
	created_at = str(current_timestamp.strftime("%Y-%m-%d %H:%M:%S"))
	
	service = str(form_data["service"])
	resources = int(form_data["resources"])
	minhistory = int(form_data["minhistory"])
	shots = int(form_data["shots"])
	profit_loss= int(form_data["profit_loss"])
	transaction_type = str(form_data["transaction_type"])
	execution_time = float(form_data["execution_time"])
	operation_cost = float(form_data["operation_cost"])
	total_profit = float(form_data["total_profit"])
	total_loss = float(form_data["total_loss"])
	warmup_time = round(float(form_data["warmup_time"]),3)
	var95_avg = float(form_data["var95_avg"])
	var99_avg = float(form_data["var99_avg"])
	
	sql = f"INSERT INTO {db_table_name} (created_at, service, resources, minhistory, shots, profit_loss, transaction_type, execution_time, warmup_time, operation_cost, total_profit, total_loss, var95_avg, var99_avg) VALUES (\"{created_at}\", \"{service}\", {resources}, {minhistory}, {shots}, {profit_loss}, \"{transaction_type}\", {execution_time}, {warmup_time}, {operation_cost}, {total_profit}, {total_loss}, {var95_avg}, {var99_avg})"
	
	with connection.cursor() as cursor:
		cursor.execute(sql)

	connection.commit()
	
# READ DATA
def read_data(connection, db_table_name):
	
	sql = '''SELECT * FROM ''' + db_table_name
	
	results = None
	with connection.cursor() as cursor:
		cursor.execute(sql)
		results = cursor.fetchall()

	connection.commit()
	
	return results


connection = None
db_table_name = "audit_history_table"
def db_session(access_key_id, secret_access_key, session_token, name_of_region, security_group_id_db):

	global time_to_connect_to_db, connection

	time_to_connect_to_db = time.time()
	session = boto3.Session(aws_access_key_id= access_key_id, aws_secret_access_key= secret_access_key, aws_session_token = session_token, region_name=name_of_region)

	# Create an RDS client
	rds = session.client('rds')

	# Parameters of DB to initialize DB instance
	db_parameters = {}

	db_parameters["db_instance_identifier"] = 'auditdbinstance'
	db_parameters["db_name"] = 'auditdb'
	db_parameters["db_username"] = 'admin'
	db_parameters["db_password"] = 'admin4321'

	db_parameters["db_instance_class"] = 'db.t2.micro'
	db_parameters["engine"] = 'mysql'
	db_parameters["engine_version"] = '8.0.32'
	db_parameters["allocated_storage"] = 20
	db_parameters["VPCSecurityGroup"] = [security_group_id_db]
	
	# Get Connection Object
	connection = get_connection(rds, db_parameters)
	
	time_to_connect_to_db = time.time() - time_to_connect_to_db
	

# Creates DB Instance (RUN ONLY ONCE)
#create_db_instance(rds, db_parameters)

# Create TABLE (RUN ONLY ONCE)
want_to_create_table = False
if want_to_create_table == True:
	try:
		create_table(connection, db_table_name)
		print('Table Created')
	except:
		print('Table Already Exists')
# --------------------------- AWS RDS Database (Audit Log) ---------------------------------
# --------------------------- AWS EC2 Instance ---------------------------------------------

# Creating session for EC2
session_2 = boto3.Session(aws_access_key_id= access_key_id, aws_secret_access_key= secret_access_key, aws_session_token = session_token, region_name=name_of_region)

ec2 = session_2.client('ec2')

# Creates Instances and returns response, which is used to get public ip's
def create_instance(ec2, form_data):
	resources = int(form_data["resources"])

	response = ec2.run_instances(ImageId=ubuntu_image_id, InstanceType='t2.micro', KeyName=name_of_key, SecurityGroups=[security_group_id_ec2], MinCount=resources, MaxCount=resources)
	return response
	
	
# Terminating the running instances
def terminate_instances(ec2, instance_id_list):

	ec2.terminate_instances(InstanceIds = instance_id_list)
	
	return 'Termination Success'
	

# Function that returns the list of instance id's
def get_instance_id_list(response, form_data):

	resources = int(form_data["resources"])

	instance_id_list = []
	
	for i in range(0, resources):
		instance_id_list.append(response['Instances'][i]['InstanceId'])
	
	return instance_id_list

	
# Function that returns the list of public ip's
def get_public_ip_list(response, form_data):

	resources = int(form_data["resources"])
	
	public_ip_address_list = []
	
	for i in range(0, resources):
		public_ip_address_list.append(response['Reservations'][0]['Instances'][i]['PublicIpAddress'])
	
	return public_ip_address_list
	
	
# Terminating the running instances of the AWS EC2.
def terminate_instances(ec2, instance_id_list):

	response = ec2.terminate_instances(InstanceIds = instance_id_list)



def execute_ssh_command(ip, username, pem_file, command):

	client = paramiko.SSHClient()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	client.connect(ip, username = username, key_filename = pem_file)
	
	# Reading the output/error from the AWS EC2 CLI and returning them
	stdin, stdout, stderr = client.exec_command(command)
	output = stdout.read().decode('utf-8')

	client.close()

	return output
	
# Code to run ssh commands parallely across the EC2 instances. 
def execute_ssh_commands_parallel(public_ips, username, pem_file, command):

	results = {}

	with concurrent.futures.ThreadPoolExecutor() as executor:
	
		futures = {executor.submit(execute_ssh_command, ip, username, pem_file, command): ip for ip in public_ips}
		
		for future in concurrent.futures.as_completed(futures):

			host = futures[future]
			try:
				output = future.result()
				results[host] = output
				
			except Exception as e:
                		results[host] = str(e)

	return results

# EC2 Functions -

# 1. Once EC2 is initialized and running, it will download the risk_values.py file from Github (public repository), and pass in arguments in the CLI.
# 2. It will print the outputs, and is captured from the terminal.
# 3. Heavy string manipulation and processing is used.

def ec2_function(form_data):

	results_dict_list = []
	
	public_ips = form_data["public_ip"]
	
	minhistory = ' '+str(form_data["minhistory"])
	shots = ' '+str(form_data["shots"])
	transaction_type = ' '+str(form_data["transaction_type"])

	data_list = json.dumps(form_data['data_list_q'])
	data_list_q = f" '{data_list}'"
	
	# SSH Command to run in CLI
	command = 'git clone https://github.com/shaikhahmad179/riskanalysis.git;cd riskanalysis;python3 risk_values.py' + minhistory + shots + transaction_type + data_list_q
	
	username = ubuntu_image_username
	pem_file = pem_file_name
	
	# Runs the commands parallelly across the active running EC2 instances.
	results = execute_ssh_commands_parallel(public_ips, username, pem_file, command)
	
	counter = 0
	# String Manipulation and Data Processing
	for host, output in results.items():
	
		output = output.rstrip("\n")
		output = ast.literal_eval(output)
	
		results_dict = {}
	
		results_dict[str(counter)] = output
		counter = counter + 1
		results_dict_list.append(results_dict)

	return results_dict_list
	

# Generates cost for Ec2
def get_ec2_cost(execution_time, warmup_time, resources):
	
	resources = int(resources)
	total_time = execution_time + warmup_time
	
	op_cost = total_time * (0.0116/3600) * resources
	op_cost = float("{:.3e}".format(op_cost))
	
	return op_cost
# --------------------------- AWS EC2 Instance ---------------------------------------------
# --------------------------- Multithreading in Lambda -------------------------------------
# Multi-threaded Lambda Function that requires form_data, and returns a list of list of data. (Referred from Lab 3)
def lambda_function(form_data):

	parallel = int(form_data["resources"])
	runs=[value for value in range(parallel)]
	json_ = json.dumps(form_data)

	def getpage(id):
		try:
			c = http.client.HTTPSConnection(lambda_endpoint)
			c.request("POST",function_name_lambda, json_)
			response = c.getresponse()
			data = response.read().decode('utf-8')
			data = ast.literal_eval(data)
			
		except IOError:
			print( 'Failed to open ', host )
		 
		return {str(id) : data}

	def getpages():
		with ThreadPoolExecutor() as executor:
			results=executor.map(getpage, runs)
			
		return results
	
	return getpages()

# Generates cost for Lambda
def get_lambda_cost(execution_time, warmup_time, resource):

	resource = int(resource)
	
	total_time = execution_time + warmup_time
	
	op_cost = total_time * 0.0000021
	op_cost = float("{:.3e}".format(op_cost))
	
	return op_cost

# --------------------------- Multithreading in Lambda -------------------------------------
# After getting data from Parallelization, data goes through a series of processing and transformation.
def get_data_for_rendering(results, df, days_to_add, transaction_type, service):
	
	#Iterates the list of dictionaries produced while parallelization, and changes structure
	concatendated_dict = {}	
	for r in results:
		for key, item in r.items():
			concatendated_dict[key] = item
	
	# Groups by the date
	grouped_data = {}
	for key, value in concatendated_dict.items():
	
		for sub_list in value:
		
			date = sub_list[0]
			
			if date in grouped_data:
			
				grouped_data[date][0] += sub_list[1]
				grouped_data[date][1] += sub_list[2]
				
			else:
				grouped_data[date] = [sub_list[1], sub_list[2]]
	
	# Averages the risk values from parallelization
	for key, value in grouped_data.items():
		av1 = value[0] / len(concatendated_dict.keys())
		av2 = value[1] / len(concatendated_dict.keys())
		value[0] = av1
		value[1] = av2
		
	list_of_data = []
	total_profit = []
	total_loss = []
	
	# Calculate Profit/Loss Amount
	# This also calculates the new data which is 'P' days after to buy/sell
	for key, value in grouped_data.items():
	
		old_date = key
		old_date_idx = int(df.loc[df['Date'] == old_date].index.values)
		
		new_date_idx = days_to_add + old_date_idx
		
		if new_date_idx <= len(df):
		
			new_date = df.iloc[new_date_idx][0]

			#Closing Price
			closing_old_price = float(df.iloc[old_date_idx][4])
			closing_new_price = float(df.iloc[new_date_idx][4])
			
			profit_loss = ""
			
			#Buy
			if transaction_type == 'buy':
				
				# Profit
				if closing_new_price > closing_old_price:
					amount = closing_new_price - closing_old_price
					profit_loss = "Profit"
					total_profit.append(amount)
					
				# Loss
				else:
					amount = closing_new_price - closing_old_price
					profit_loss = "Loss"
					total_loss.append(amount)
				
				amount = round(amount, 3)
				list_of_data.append([old_date, value[0], value[1], profit_loss, amount])
				
			#Sell
			else:
			
				# Loss
				if closing_new_price > closing_old_price:
					amount = closing_old_price - closing_new_price
					profit_loss = "Loss"
					total_loss.append(amount)
					
				# Profit
				else:
					amount = closing_old_price - closing_new_price
					profit_loss = "Profit"
					total_profit.append(amount)
				
				amount = round(amount, 3)
				list_of_data.append([old_date, value[0], value[1], profit_loss, amount])
				
		else:
			list_of_data.append([old_date, value[0], value[1], '---', 'None'])
	
	total_profit = 	round(sum(total_profit), 3)
	total_loss = round(sum(total_loss), 3)
	
	return [list_of_data, total_profit, total_loss]
		
# Render function (Got from Lab1)
def doRender(tname, values={}):
	if not os.path.isfile( os.path.join(os.getcwd(), 'templates/'+tname) ):
		return render_template('index.html')
		
	return render_template(tname, **values)
# ------------------------------ CHART FUNCTION -------------------------------------------
# Generates chart - can be viewed in Results Page.
def chart(data):

	url = 'https://image-charts.com/chart'
	
	date_list = []
	var_95_list = []
	var_99_list = []
	profit_loss_amount_list = []
	
	for row in data:
		date_list.append(row[0])
		var_95_list.append(row[1])
		var_99_list.append(row[2])
		profit_loss_amount_list.append(row[4])
	
	# Chart 1 - Risk Values and Trends
	var_95_avg = sum(var_95_list)/len(var_95_list)
	var_95_avg_list = [var_95_avg] * len(var_95_list)
	var_99_avg = sum(var_99_list)/len(var_99_list)
	var_99_avg_list = [var_99_avg] * len(var_99_list)
	
	var_95_str = ','.join(map(str, var_95_list))
	var_99_str = ','.join(map(str, var_99_list))
	var_95_avg_str = ','.join(map(str, var_95_avg_list))
	var_99_avg_str = ','.join(map(str, var_99_avg_list))
	
	chd = f"a:{var_95_str}|{var_99_str}|{var_95_avg_str}|{var_99_avg_str}"
	chxl = "0:|" + "|".join(date_list)
	
	chart_1 = {
	'chco':'d43b3b,0000FF,f38674,8ca6f1',
	'chd': chd,
	'chdl': 'Var95|Var99',
	'chdlp':'b',
	'chg':'1,2',
	'chs':'830x400',
	'cht':'ls',
	'chtt':'Risk',
	'chxl': chxl,
	'chxt':'x,y',
	'chxs':'0,min90',
	'chls':'1.5|1.5', 
	'chma':'25,25,10,10'
	}
	
	data = urllib.parse.urlencode(chart_1).encode('ascii')
	response = requests.post(url, data=data)
	img_bytes = BytesIO(response.content)
	img_data_1 = base64.b64encode(img_bytes.getvalue()).decode('ascii')
	
	# Returns the image data, averages of var95 and var99 for further processing
	return [img_data_1, var_95_avg, var_99_avg]
	
# ------------------------------ CHART FUNCTION ---------------------------------------------
form_data = {}
# Calculate Endpoint - To Calculate Risk Analysis of Var95 and Var99 and other values.
@app.route('/calculate', methods=['POST'])
def calculateHandler():
	if request.method == 'POST':
		
		global form_data, connection
		
		form_data["minhistory"] = str(request.form.get("length_of_price_history"))
		form_data["shots"] = str(request.form.get("num_of_data_points"))
		form_data["profit_loss"] = str(request.form.get("profit_loss"))
		form_data["transaction_type"] = str(request.form.get("buy_sell"))
		form_data["data_list"] = str(data_list)
		form_data["data_list_q"] = data_list
		
		# Lambda
		if form_data["service"] == "lambda":
		
			if form_data["warmup_status"] == True:
			
				start_time = time.time()
				results = lambda_function(form_data)
				
				# Calculating time elapsed and Total Operating Cost (Warm Up + Execution)
				form_data["warmup_time"] = form_data["warmup_time"] + time_to_connect_to_db
				form_data["execution_time"] = round(time.time() - start_time, 3)
				form_data["operation_cost"] = get_lambda_cost(form_data["execution_time"], form_data["warmup_time"], form_data["resources"])
				form_data["total_time"] = round(form_data["operation_cost"] + form_data["warmup_time"], 3)
				
				processed_data_list = get_data_for_rendering(results, data, int(form_data["profit_loss"]), form_data["transaction_type"], form_data["service"])
				data_ = processed_data_list[0]
				form_data['data_'] = data_
				
				form_data["total_profit"] = processed_data_list[1]
				form_data["total_loss"] = processed_data_list[2]
				
				img_data_list = chart(data_)
				form_data['img_data_1'] = img_data_list[0]
				
				form_data["var95_avg"] = round(img_data_list[1],5)
				form_data["var99_avg"] = round(img_data_list[2],5)
				
				#Insert into AWS RDS for Audit Log
				insert_data(connection, form_data, db_table_name)
				
				form_data["msg"] = ""
				
				return doRender('output.html', {'form_data' : form_data})
				
		
		# EC2
		else:	
			# If user warms up the resources, only then can calculate.
			if form_data["warmup_status"] == True:
			
				start_time = time.time()
			
				results = ec2_function(form_data)
				
				# Calculating time elapsed and Total Operating Cost (Warm Up + Execution)
				form_data["warmup_time"] = form_data["warmup_time"] + time_to_connect_to_db
				form_data["execution_time"] = round(time.time() - start_time, 3)
				form_data["operation_cost"] = get_ec2_cost(form_data["execution_time"], form_data["warmup_time"], form_data["resources"])
				form_data["total_time"] = round(form_data["operation_cost"] + form_data["warmup_time"], 3)
				
				processed_data_list = get_data_for_rendering(results, data, int(form_data["profit_loss"]), form_data["transaction_type"], form_data["service"])
				data_ = processed_data_list[0]
				form_data['data_'] = data_
				
				form_data["total_profit"] = processed_data_list[1]
				form_data["total_loss"] = processed_data_list[2]
				
				img_data_list = chart(data_)
				form_data['img_data_1'] = img_data_list[0]
				
				form_data["var95_avg"] = round(img_data_list[1], 5)
				form_data["var99_avg"] = round(img_data_list[2], 5)
				
				#Insert into AWS RDS for Audit Log
				insert_data(connection, form_data, db_table_name)
				
				form_data["msg"] = ""
				
				return doRender('output.html', {'form_data' : form_data})
				
			# If User tries to calculate without warming up the resources
			else:
				return doRender('index.html', {'warmup_required_msg' : 'Need to warmup the resources'})
				
# Endpoint for Audit Handler. This retriever data from the AWS RDS Database	
@app.route('/audit', methods=['POST'])
def audit_handler():
	
	global connection
	
	list_of_audit_logs = []
	total_operation_cost = []
	
	#List of Audit Data
	list_of_audit_results = read_data(connection, db_table_name)
	for r in list_of_audit_results:
		x = []
		for y in r:
			x.append(y)
		
		list_of_audit_logs.append(x)
		total_operation_cost.append(x[9])
		
	total_operation_cost = sum(total_operation_cost)
	total_operation_cost = float("{:.3e}".format(total_operation_cost))
	
	return doRender('audit.html', {'data': list_of_audit_logs, 'total_operation_cost': total_operation_cost})

# Warms up the necessary resources - EC2 and Lambda
@app.route('/warmup', methods = ["POST"])
def warmup():
	if request.method == 'POST':
		
		db_session(access_key_id, secret_access_key, session_token, name_of_region, security_group_id_db)
		global form_data
		
		form_data["service"] = str(request.form.get("service"))
		form_data["resources"] = str(request.form.get("resources"))

		reset_data = {'service': form_data["service"], "resources": form_data["resources"] }
		
		# Lambda
		if form_data["service"] == "lambda":
			
			form_data["warmup_time"] = round(time_to_load_data, 3)

			form_data["warmup_status"] = True
			
			return doRender('output.html', {'form_data': reset_data})
			
		# EC2 - Creates instances and gets public ip
		else:
			start_time = time.time()
			
			response = create_instance(ec2, form_data)
			instance_id_list = get_instance_id_list(response, form_data)
			
			form_data["instance_id_list"] = instance_id_list
			
			#Wait for the instance is running
			ec2.get_waiter('instance_running').wait(InstanceIds=instance_id_list)
			
			response = ec2.describe_instances(InstanceIds=instance_id_list)
			public_ip_address_list = get_public_ip_list(response, form_data)
			
			time.sleep(30)
			
			form_data["warmup_time"] = (time.time() - start_time) + time_to_load_data
			form_data["warmup_time"] = round(form_data["warmup_time"], 3)
			form_data["public_ip"] = public_ip_address_list
			
			form_data["warmup_status"] = True
			
			return doRender('output.html', {'form_data': reset_data})
			

# For EC2 Services, it will terminate the running instances
@app.route('/terminate', methods=['POST'])
def terminate_handler():

	global form_data
	
	if form_data["service"] == "ec2":
	
		if form_data["warmup_status"] == True:
		
			terminate_instances(ec2, form_data["instance_id_list"])
			form_data['msg'] = "Terminated "+ str(len(form_data["instance_id_list"])) + " Instances"
			form_data["warmup_status"] = False
			
			return doRender('output.html', {'form_data' : form_data})
			
		# If User tries to terminate again, once terminated
		else:
			
			form_data["msg"] = "Instances already terminated"
			
			return doRender('output.html', {'form_data' : form_data})
	
	# Error Handling - User gets prompted message if he tries to terminate with Lambda	
	else:
	
		form_data["msg"] = "Termination is only for EC2"
		
		return doRender('output.html', {'form_data' : form_data})
		
		
# This will reset the analysis in the Reset Page
@app.route('/reset', methods=['POST'])
def reset_handler():
	reset_data = {'service': form_data["service"], "resources": form_data["resources"] }
	return doRender('output.html', {'form_data' : reset_data})
					
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def mainPage(path):
	return doRender(path)

@app.errorhandler(500)
def server_error(e):
    logging.exception('ERROR!')
    return """
    An  error occurred: <pre>{}</pre>
    """.format(e), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
