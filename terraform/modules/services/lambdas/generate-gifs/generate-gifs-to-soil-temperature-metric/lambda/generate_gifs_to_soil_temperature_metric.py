import json
import boto3
import base64
import os
from PIL import Image
import io

# Inicialize o cliente Bedrock
bedrock = boto3.client(service_name='bedrock-runtime')

def generate_image(prompt):
    body = json.dumps({
        "modelId": "stability.stable-diffusion-xl-v0",
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": prompt,
            "negativeText": "low quality, blurry",
            "height": 512,
            "width": 512,
            "cfgScale": 7,
            "seed": 0,
            "steps": 50,
            "style": "photographic"
        }
    })

    response = bedrock.invoke_model(body=body, modelId="stability.stable-diffusion-xl-v0", contentType="application/json", accept="application/json")
    response_body = json.loads(response.get('body').read())
    
    return base64.b64decode(response_body['images'][0])

def create_gif(images, output_path):
    frames = [Image.open(io.BytesIO(img)) for img in images]
    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=1000, loop=0)

def lambda_handler(event, context):
    temperature_levels = [5, 15, 25, 35, 45]  # Diferentes níveis de temperatura do solo em Celsius
    
    images = []
    for temp in temperature_levels:
        if temp < 15:
            color = "azul"
        elif temp < 30:
            color = "verde"
        else:
            color = "vermelho"
        
        prompt = f"Corte transversal do solo com termômetro mostrando {temp}°C. Solo com tonalidade {color}. Sementes e raízes reagindo à temperatura. Estilo fotorrealista."
        image = generate_image(prompt)
        images.append(image)
    
    # Criar o GIF
    gif_path = '/gif/soil_temperature/soil_temperature.gif'
    create_gif(images, gif_path)
    
    # Salvar o GIF em um bucket S3
    s3 = boto3.client('s3')
    bucket_name = 'soil_temperature_media_bucket'
    
    with open(gif_path, 'rb') as gif_file:
        s3.put_object(Bucket=bucket_name, Key='soil_temperature.gif', Body=gif_file)
    
    return {
        'statusCode': 200,
        'body': json.dumps('GIF da temperatura do solo gerado e salvo com sucesso!')
    }