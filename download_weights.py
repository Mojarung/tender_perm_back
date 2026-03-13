import os
import urllib.request
import subprocess
import sys

def download_file(url, filename):
    print(f"Downloading {filename}...")
    urllib.request.urlretrieve(url, filename)
    print(f"Saved to {filename}")

def main():
    os.makedirs("model_weights", exist_ok=True)
    
    gguf_url = "https://huggingface.co/Qwen/Qwen2-0.5B-Instruct-GGUF/resolve/main/qwen2-0_5b-instruct-q4_k_m.gguf"
    gguf_path = os.path.join("model_weights", "qwen-slm.gguf")
    
    if not os.path.exists(gguf_path):
        download_file(gguf_url, gguf_path)
    else:
        print("GGUF model already exists.")
        
    onnx_dir = os.path.join("model_weights", "ru-e5-small-onnx")
    if not os.path.exists(onnx_dir):
        print("Exporting ru-e5-small to ONNX... This might take a few minutes.")
        subprocess.run(["uv", "pip", "install", "optimum[onnxruntime]", "transformers", "torch"], check=True)
        subprocess.run(["optimum-cli", "export", "onnx", "--model", "intfloat/multilingual-e5-small", "--task", "feature-extraction", onnx_dir], check=True)
        print("ONNX export complete.")
    else:
        print("ONNX model already exists.")

if __name__ == "__main__":
    main()
