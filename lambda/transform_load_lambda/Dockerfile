FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY lambda/transform_load_lambda/lambda_function.py .
COPY src/transform.py .
COPY src/load.py .

CMD ["lambda_function.lambda_handler"]