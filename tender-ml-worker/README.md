# Tender ML Worker

Internal ML microservice for the Tender NMCC system.

## Models

| Task | Model | Format | Runtime |
|------|-------|--------|---------|
| Embeddings | ai-forever/ru-e5-small | ONNX INT8 | onnxruntime |
| Characteristics parsing | Qwen2.5-0.5B-Instruct | GGUF Q4_K_M | llama-cpp-python |
| Outlier detection | IsolationForest | in-memory | scikit-learn |
