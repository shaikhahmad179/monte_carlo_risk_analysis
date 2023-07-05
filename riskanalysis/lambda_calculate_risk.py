import math
import random
import ast

def lambda_handler(event, context):
    
    list_of_data = []
    
    service = event["service"]
    resources = int(event["resources"])
    minhistory = int(event["minhistory"])
    shots = int(event["shots"])
    profit_loss = int(event["profit_loss"])
    transaction_type = event["transaction_type"]
    data_list = event["data_list"]
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
