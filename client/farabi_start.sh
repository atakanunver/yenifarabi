#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"
exec venv/bin/python3 main.py
