#!/bin/bash
cat << 'SECRET' > scratch/plain.yaml
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
  namespace: default
data:
  key1: dmFsMQ==
  key2: dmFsMg==
SECRET

kubeseal --format yaml < scratch/plain.yaml > scratch/sealed.yaml
echo "INITIAL SEALED:"
cat scratch/sealed.yaml
echo ""

cat << 'SECRET2' > scratch/plain.yaml
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
  namespace: default
data:
  key1: bmV3dmFsMQ==
  key3: dmFsMw==
SECRET2

kubeseal --format yaml --merge-into scratch/sealed.yaml < scratch/plain.yaml
echo "AFTER MERGE:"
cat scratch/sealed.yaml
