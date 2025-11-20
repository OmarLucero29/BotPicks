#!/bin/bash

echo "Buscando archivos no trackeados..."

# Detectar todos los archivos NO trackeados (excepto cachés y .venv)
UNTRACKED_FILES=$(git ls-files --others --exclude-standard | sort)

echo "=== Archivos NO trackeados detectados ==="
echo "$UNTRACKED_FILES"
echo "========================================="
echo

if [ -z "$UNTRACKED_FILES" ]; then
    echo "No hay archivos no trackeados."
    exit 0
fi

read -p "¿Agregar TODOS estos archivos al repo? (s/n) " yn
if [ "$yn" != "s" ]; then
    echo "Abortado."
    exit 0
fi

echo "Agregando archivos..."

# Añadir todos los archivos uno por uno
while IFS= read -r f; do
    echo "git add \"$f\""
    git add "$f"
done <<< "$UNTRACKED_FILES"

echo
git status --porcelain
echo

read -p "¿Crear commit y push a main? (s/n) " yn2
if [ "$yn2" != "s" ]; then
    echo "Abortado."
    exit 0
fi

git commit -m "chore: add all untracked files from Codespace"
git push origin main

echo "=== COMPLETADO ==="
