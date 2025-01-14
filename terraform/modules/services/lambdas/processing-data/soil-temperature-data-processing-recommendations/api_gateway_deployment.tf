# Deployment do API Gateway
resource "aws_api_gateway_deployment" "soil_temperature_data_processing_recommendations_api_deployment" {
  depends_on = [
    aws_api_gateway_integration.get_recommendations_integration,
    aws_api_gateway_integration.get_recommendations_by_topic_integration,
    aws_api_gateway_integration.get_temperature_integration,
    aws_api_gateway_integration.post_generate_recommendations_integration
  ]

  rest_api_id = aws_api_gateway_rest_api.soil_temperature_data_processing_recommendations_api.id
  stage_name    = "prod"

  lifecycle {
    create_before_destroy = true
  }

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.recommendations.id,
      aws_api_gateway_resource.recommendations_by_topic.id,
      aws_api_gateway_resource.temperature.id,
      aws_api_gateway_resource.generate_recommendations.id,
      aws_api_gateway_method.get_recommendations.id,
      aws_api_gateway_method.get_recommendations_by_topic.id,
      aws_api_gateway_method.get_temperature.id,
      aws_api_gateway_method.post_generate_recommendations.id,
      aws_api_gateway_integration.get_recommendations_integration.id,
      aws_api_gateway_integration.get_recommendations_by_topic_integration.id,
      aws_api_gateway_integration.get_temperature_integration.id,
      aws_api_gateway_integration.post_generate_recommendations_integration.id,
    ]))
  }
}

# Estágio do API Gateway
//resource "aws_api_gateway_stage" "prod" {
//  deployment_id = aws_api_gateway_deployment.soil_temperature_data_processing_recommendations_api_deployment.id
//  rest_api_id   = aws_api_gateway_rest_api.soil_temperature_data_processing_recommendations_api.id
//  stage_name    = "prod"
//}