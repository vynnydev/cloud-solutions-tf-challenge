import json
import boto3
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
import uuid
import logging
import time
import re
from decimal import Decimal

# Configuração do logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Inicialização dos clientes AWS
bedrock = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')

# Definição das tabelas DynamoDB
soil_temperature_task_plan_table = dynamodb.Table('AISoilTemperatureTaskPlans')
soil_temperature_history_table = dynamodb.Table('SoilTemperatureHistory')
soil_temperature_averages_table = dynamodb.Table('SoilTemperatureAverages')

# Constantes
MAX_TOKENS = 2000
TEMPERATURE = 0.5
TOP_P = 0.9

# Custom JSON Encoder para lidar com objetos Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    logger.info(f"Evento recebido: {json.dumps(event)}")
    
    try:
        if 'httpMethod' in event:
            if event['httpMethod'] == 'GET':
                # Verifica se o path termina com 'task-plan'
                if event.get('path', '').endswith('/task-plan'):
                    return get_all_task_plans()
                elif 'queryStringParameters' in event and event['queryStringParameters']:
                    return handle_get_request(event)
                else:
                    return create_response(400, "Parâmetros de consulta ausentes ou inválidos.")
            else:
                return create_response(405, "Método HTTP não permitido.")
        elif 'Records' in event:
            return handle_dynamodb_event(event['Records'])
        elif 'temperature' in event:
            logger.info("Processando dados de temperatura do solo do evento")
            return process_temperature_data(event)
        else:
            logger.info("Coletando dados de temperatura do solo do banco de dados")
            return handle_database_event()
    except Exception as e:
        logger.error(f"Erro no lambda_handler: {str(e)}")
        return create_response(500, f"Erro interno: {str(e)}")

def handle_get_request(event):
    query_params = event.get('queryStringParameters', {})
    if query_params and 'taskId' in query_params:
        return get_task_plan(query_params['taskId'])
    elif query_params and 'recommendations' in query_params:
        return get_recommendations(query_params['recommendations'])
    else:
        return create_response(400, "Parâmetros de consulta inválidos.")

def handle_dynamodb_event(records):
    for record in records:
        if record['eventName'] == 'INSERT':
            new_image = record['dynamodb']['NewImage']
            logger.info(f"Novo registro inserido na tabela SoilTemperatureHistory: {json.dumps(new_image)}")
            return process_temperature_data(new_image)
    return create_response(200, "Eventos processados com sucesso.")

def handle_database_event():
    temperature_data = get_latest_temperature_from_averages()
    if not temperature_data:
        temperature_data = get_latest_temperature_from_history()
    
    if temperature_data:
        return process_temperature_data(temperature_data)
    else:
        logger.error("Não foi possível obter dados de temperatura do solo de nenhuma tabela")
        return create_response(404, "Dados de temperatura do solo não encontrados")

def get_latest_temperature_from_averages():
    try:
        logger.info("Obtendo a última temperatura do solo da tabela SoilTemperatureAverages")
        response = soil_temperature_averages_table.scan(Limit=1)
        items = response.get('Items', [])
        if items:
            latest_item = items[0]
            return {
                'temperature': latest_item['averageTemperature'],
                'status': latest_item.get('status', 'unknown'),
                'timestamp': latest_item['timestamp']
            }
        return None
    except Exception as e:
        logger.error(f"Erro ao obter temperatura do solo da tabela SoilTemperatureAverages: {str(e)}")
        return None

def get_latest_temperature_from_history():
    try:
        logger.info("Obtendo a última temperatura do solo da tabela SoilTemperatureHistory")
        response = soil_temperature_history_table.scan(Limit=1)
        items = response.get('Items', [])
        if items:
            latest_item = items[0]
            return {
                'temperature': latest_item['averageTemperature'],
                'status': latest_item.get('status', 'unknown'),
                'timestamp': latest_item['timestamp']
            }
        return None
    except Exception as e:
        logger.error(f"Erro ao obter temperatura do solo da tabela SoilTemperatureHistory: {str(e)}")
        return None

def get_task_plan(task_id):
    try:
        response = soil_temperature_task_plan_table.get_item(Key={'planId': task_id})
        item = response.get('Item')
        if item:
            return create_response(200, json.dumps(item, cls=DecimalEncoder), get_cors_headers())
        else:
            return create_response(404, "Plano de tarefas não encontrado", get_cors_headers())
    except Exception as e:
        logger.error(f"Erro ao obter plano de tarefas: {str(e)}")
        return create_response(500, f"Erro ao obter plano de tarefas: {str(e)}", get_cors_headers())

def get_all_task_plans():
    try:
        logger.info("Iniciando get_all_task_plans")
        response = soil_temperature_task_plan_table.scan()
        logger.info(f"Resposta do scan: {response}")
        items = response.get('Items', [])
        logger.info(f"Items recuperados: {items}")
        return create_response(200, json.dumps(items, cls=DecimalEncoder), get_cors_headers())
    except Exception as e:
        logger.error(f"Erro ao obter todos os planos de tarefas: {str(e)}")
        return create_response(500, f"Erro ao obter todos os planos de tarefas: {str(e)}", get_cors_headers())

def process_temperature_data(data):
    try:
        logger.info(f"Dados recebidos para processamento: {data}")
        
        # Normalizando os dados recebidos
        data = normalize_input_data(data)
        
        temperature = data.get('temperature')
        status = data.get('status')
        crops = data.get('crops')  # Recebendo a lista de culturas
        
        logger.info(f"Dados normalizados: temperature={temperature}, status={status}, crops={crops}")
        
        # Validando temperatura do solo
        if not validate_temperature_data(temperature):
            return create_response(400, 'Dados de temperatura do solo inválidos ou ausentes')

        # Gerando o plano de tarefas com a IA
        logger.info(f"Processando dados de temperatura do solo: temperature={temperature}, status={status}, crops={crops}")
        
        new_plan = generate_task_plan_with_ai(temperature, status, crops)
        if new_plan:
            plan_id = store_task_plan(new_plan, temperature, status)
            if plan_id:
                logger.info(f"Plano de tarefas armazenado com sucesso. ID: {plan_id}")
                return create_response(200, f'Novo plano de tarefas gerado e armazenado com ID: {plan_id}')
            else:
                logger.error("Falha ao armazenar o plano de tarefas")
                return create_response(500, 'Falha ao armazenar o plano de tarefas')
        else:
            logger.error("Falha ao gerar o plano de tarefas")
            return create_response(500, 'Falha ao gerar o plano de tarefas')
    
    except ValueError as ve:
        logger.error(f"Erro de validação: {str(ve)}")
        return create_response(400, f"Erro de validação: {str(ve)}")
    except Exception as e:
        logger.error(f"Erro ao processar dados de temperatura do solo: {str(e)}")
        return create_response(500, f"Erro ao processar dados de temperatura do solo: {str(e)}")

def normalize_input_data(data):
    if isinstance(data, str):
        logger.info("Dados recebidos como string. Convertendo para dicionário.")
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("Falha ao decodificar a string JSON")
    
    if not isinstance(data, dict):
        raise ValueError(f"Formato de dados inesperado: {type(data)}")
    
    return data

def validate_temperature_data(temperature):
    if temperature is None:
        logger.error("Dados de temperatura do solo ausentes")
        return False
    
    try:
        temperature_value = Decimal(str(temperature))
        if temperature_value < 0 or temperature_value > 100:
            logger.error(f"Valor de temperatura do solo fora do intervalo válido: {temperature_value}")
            return False
    except ValueError:
        logger.error(f"Valor de temperatura do solo não é um número válido: {temperature}")
        return False
    
    return True

def get_recommendations(topic):
    try:
        recommendation_prompt = f"""Forneça recomendações detalhadas para {topic} em uma fazenda, considerando práticas agrícolas modernas e sustentáveis."""
        
        prompt = "Human: " + recommendation_prompt + "\n\nAssistant:"
        
        logger.info("Enviando prompt para o modelo de IA para o auxílio recomendação das tarefas...")
        response = bedrock.invoke_model(
            modelId="anthropic.claude-v2",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 300,
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
            })
        )
        
        response_body = json.loads(response['body'].read())
        recommendations = response_body['completion']
        return create_response(200, recommendations.strip())
    except Exception as e:
        logger.error(f"Erro ao obter recomendações para {topic}: {str(e)}")
        return create_response(500, f"Erro ao obter recomendações: {str(e)}")

def generate_task_plan_with_ai(temperature, status, crops):
    timestamp = int(time.time())
    logger.info(f"[{timestamp}] Iniciando geração do plano de tarefas")
    logger.info(f"[{timestamp}] Parâmetros recebidos - Umidade: {temperature}%, Status: {status}, Culturas: {crops}")

    try:
        current_date = datetime.now()
        start_date = current_date.strftime("%Y-%m-%d")  # Mantendo start_date como string aqui

        # Criando a lista de culturas no formato de string para o prompt
        crops_str = ", ".join(crops)

        # Novo prompt que inclui as culturas e tarefas
        prompt = f'''Human: Com base em uma temperatura do solo de {temperature}°C e status '{status}', gere um plano de tarefas agrícola para as próximas 4 semanas para as culturas {crops_str}.
        Inclua datas e horários exatos para cada tarefa. Cada semana deve ter uma sequência de ações específicas relacionadas às {crops_str}, práticas agrícolas modernas e sustentáveis, começando a partir de {start_date}.
        O plano deve cobrir:
        1. Monitoramento da temperatura do solo e ajustes na irrigação para evitar superaquecimento.
        2. Introdução de técnicas para manter a temperatura ideal do solo, como coberturas vegetais.
        3. Avaliar o impacto da temperatura no crescimento das plantas e ajustar práticas agrícolas.
        4. Identificar áreas de solo com temperaturas extremas e propor soluções de manejo.

        Além disso, forneça recomendações semanais sobre como adaptar o manejo agrícola a diferentes condições térmicas do solo para maximizar a produtividade.
        Assistant:'''

        logger.info(f"[{timestamp}] Enviando prompt para o modelo de IA...")
        response = bedrock.invoke_model(
            modelId="anthropic.claude-v2:1",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 400,
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "stop_sequences": ["Human:"]
            })
        )

        logger.info(f"[{timestamp}] Resposta recebida do modelo de IA!!!!")
        response_body = json.loads(response['body'].read())
        recommendations = response_body['completion'].strip()

        # Função para gerar o cronograma de tarefas com base na recomendação da IA
        def generate_task_schedule(recommendations):
            tasks_by_week = {}
            schedule_start_date = datetime.now()  # Renomeado para schedule_start_date
            
            for week in range(1, 5):  # Para 4 semanas
                tasks = []
                for day in range(7):  # Atribuindo uma tarefa por dia
                    task_date = schedule_start_date + timedelta(weeks=week-1, days=day)
                    task_time = task_date.replace(hour=9, minute=0)  # Horário fixo de 9h
                    task = {
                        "date": task_time.strftime("%Y-%m-%d"),
                        "time": task_time.strftime("%H:%M"),
                        "task": f"Tarefa diária de manutenção para {crops_str}."
                    }

                    # Adicionando recomendação semanal
                    if day == 0:  # A cada início de semana, forneça uma nova recomendação
                        task["recommendation"] = f"Recomenda-se plantar {crops_str} complementar ou alternativo, ou adotar práticas como rotação de cultura."

                    tasks.append(task)
                tasks_by_week[f"Semana {week}"] = tasks
            return tasks_by_week

        # Gerando plano de tarefas
        tasks_by_week = generate_task_schedule(recommendations)
        
        plan = {
            'planId': str(uuid.uuid4()),
            'temperature': Decimal(str(temperature)),
            'status': status,
            'crops': crops,  # Lista de culturas original
            'recommendations': recommendations,  # Recomendação geral da IA
            'tasks_by_week': tasks_by_week,  # Tarefas organizadas por semana
            'generatedAt': current_date.strftime("%Y-%m-%d")  # Use current_date aqui
        }

        return plan

    except Exception as e:
        logger.error(f"Erro ao gerar plano de tarefas: {str(e)}")
        return None

def store_task_plan(plan, temperature, status):
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"[{timestamp}] Iniciando armazenamento do plano de tarefas de temperatura do solo")
    logger.info(f"[{timestamp}] Parâmetros recebidos - Umidade: {temperature}, Status: {status}")
    
    try:
        plan_id = str(uuid.uuid4())
        logger.info(f"[{timestamp}] UUID gerado para o plano: {plan_id}")
        
        logger.info(f"[{timestamp}] Convertendo temperatura do solo para Decimal")
        temperature_decimal = Decimal(str(temperature))
        logger.info(f"[{timestamp}] Umidade convertida: {temperature_decimal}")
        
        task_item = {
            'planId': plan_id,
            'plan': plan,
            'temperature': temperature_decimal,
            'status': status,
            'createdAt': timestamp,
            'updatedAt': timestamp
        }
        
        logger.info(f"[{timestamp}] Item do plano de tarefas criado")
        logger.debug(f"[{timestamp}] Detalhes do item: {json.dumps(task_item, default=str)}")
        
        logger.info(f"[{timestamp}] Iniciando operação de put_item no DynamoDB")
        response = soil_temperature_task_plan_table.put_item(Item=task_item)
        logger.info(f"[{timestamp}] Operação put_item concluída")
        logger.debug(f"[{timestamp}] Resposta do DynamoDB: {json.dumps(response, default=str)}")
        
        logger.info(f"[{timestamp}] Plano de tarefas de temperatura do solo armazenado com sucesso. ID: {plan_id}")
        return plan_id
    except ClientError as e:
        if e.response['Error']['Code'] == 'ValidationException':
            logger.error(f"[{timestamp}] Erro de validação ao armazenar plano: {str(e)}")
            logger.error(f"[{timestamp}] Detalhes do item: {json.dumps(task_item, default=str)}")
        else:
            logger.error(f"[{timestamp}] Erro do cliente ao armazenar plano: {str(e)}")
        logger.exception("Detalhes do erro:")
        return None
    except Exception as e:
        logger.error(f"[{timestamp}] Erro inesperado ao armazenar plano de tarefas de temperatura do solo: {str(e)}")
        logger.exception("Detalhes do erro:")
        return None
    finally:
        logger.info(f"[{timestamp}] Finalizando operação de armazenamento do plano de tarefas de temperatura do solo")

def create_response(status_code, body, headers=None):
    response = {
        'statusCode': status_code,
        'body': body,
        'headers': {
            'Content-Type': 'application/json'
        }
    }
    if headers:
        response['headers'].update(headers)
    return response

def get_cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }