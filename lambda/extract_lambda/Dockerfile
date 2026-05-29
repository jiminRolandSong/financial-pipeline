FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY lambda/extract_lambda/lambda_function.py .
COPY src/extract.py .

CMD ["lambda_function.lambda_handler"]