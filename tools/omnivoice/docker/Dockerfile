FROM pytorch/pytorch:2.14.1-cuda12.6-cudnn9-devel
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake ninja-build git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.8.0 https://github.com/OHF-voice/piper1-gpl.git /opt/piper1-gpl
WORKDIR /opt/piper1-gpl
RUN python3 -m pip install --no-cache-dir -e '.[train]' && ./build_monotonic_align.sh && python3 setup.py build_ext --inplace
WORKDIR /work
