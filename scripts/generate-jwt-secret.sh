#!/bin/bash
# Генерация JWT Secret для Railway

echo "Генерирую JWT Secret..."
JWT_SECRET=$(openssl rand -hex 32)
echo ""
echo "✅ JWT_SECRET сгенерирован:"
echo ""
echo "JWT_SECRET=$JWT_SECRET"
echo ""
echo "Скопируйте эту строку и добавьте в Railway Dashboard → Variables"

