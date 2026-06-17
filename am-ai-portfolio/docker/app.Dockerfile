FROM dockerhub.citicsinfo.com/public/python:3.12.5

WORKDIR /app

SHELL ["/bin/bash", "-c"]

# 修正容器内的时区问题
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ENV UV_PROJECT_ENVIRONMENT="/usr/local/python3.12/"
ENV UV_COMPILE_BYTECODE=1

COPY pyproject.toml .
COPY uv.lock .
RUN pip install --no-cache-dir uv

# Install only the dependencies needed for the client application
# --frozen: Use exact versions from the lock file
# --only-group client: Only install dependencies marked as part of the "client" group in pyproject.toml
RUN uv sync --no-install-project --no-dev -i http://repo.citicsinfo.com/repository/pip/simple/

COPY src/ ./

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_app.py"]
