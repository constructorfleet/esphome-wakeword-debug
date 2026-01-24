from setuptools import setup, find_packages

setup(
    name="wakeword-ingest-service",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn[standard]>=0.24.0",
        "websockets>=12.0",
        "paho-mqtt>=2.0.0",
        "python-dotenv>=1.0.0",
        "numpy>=1.26.0",
    ],
    extras_require={
        "test": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
            "pytest-cov>=4.1.0",
            "httpx>=0.25.0",
        ]
    },
)
