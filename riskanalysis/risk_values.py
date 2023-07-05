# Access the command-line arguments
import math
import random
import ast
import sys

minhistory = int(sys.argv[1])
shots = int(sys.argv[2])
transaction_type = str(sys.argv[3])
data_list = str(sys.argv[4])

def risk_function(minhistory, shots, transaction_type, data_list):
    
	list_of_data = []

	data_list = ast.literal_eval(data_list)
	
	for i in range(minhistory, len(data_list)):
	
		if data_list[i][7] == 1 and transaction_type == "buy":
		
			prices = [float(data_list[j][4]) for j in range(i - minhistory, i)]
			returns = [(prices[j] - prices[j-1])/prices[j-1] for j in range(1, len(prices))]
			mean = sum(returns)/len(returns)
			std = (sum((r - mean)**2 for r in returns)/(len(returns) - 1))**0.5

			simulated = [random.gauss(mean,std) for x in range(shots)]
			simulated.sort(reverse=True)
			var95 = simulated[int(len(simulated)*0.95)]
			var99 = simulated[int(len(simulated)*0.99)]
				
			list_of_data.append([data_list[i][0], var95, var99])
			
		if data_list[i][8] == 1 and transaction_type == "sell":
		
			prices = [float(data_list[j][4]) for j in range(i - minhistory, i)]
			returns = [(prices[j] - prices[j-1])/prices[j-1] for j in range(1, len(prices))]
			mean = sum(returns)/len(returns)
			std = (sum((r - mean)**2 for r in returns)/(len(returns) - 1))**0.5

			simulated = [random.gauss(mean,std) for x in range(shots)]
			simulated.sort(reverse=True)
			var95 = simulated[int(len(simulated)*0.95)]
			var99 = simulated[int(len(simulated)*0.99)]

			list_of_data.append([data_list[i][0], var95, var99])
				
	return list_of_data
	
results = risk_function(minhistory, shots, transaction_type, data_list)
print(results)
