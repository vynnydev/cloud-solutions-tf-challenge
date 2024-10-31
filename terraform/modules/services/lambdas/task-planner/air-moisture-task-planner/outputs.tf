# Saída do URL da API
output "api_url" {
  value = aws_api_gateway_deployment.air_moisture_task_planner_deployment.invoke_url
}

output "air_moisture_task_planner_apigw_lambda_permission" {
  value = aws_lambda_permission.air_moisture_apigw_lambda_permission
}

output "air_moisture_task_planner_lambda_arn" {
  value = aws_lambda_function.air_moisture_task_planner.arn
}