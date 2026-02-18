# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OmniChat — мод для Minecraft на платформе Fabric. Версия Minecraft: 1.21.11, Java 21, Fabric Loader 0.18.4.

## Build Commands

```bash
./gradlew build          # Полная сборка мода (JAR в build/libs/)
./gradlew runClient      # Запуск Minecraft клиента с модом
./gradlew runServer      # Запуск выделенного сервера с модом
./gradlew runDatagen     # Генерация данных (data generation)
```

Используется плагин `fabric-loom` (версия 1.15-SNAPSHOT), маппинги Yarn.

## Architecture

Проект использует разделённые source sets от Loom (`splitEnvironmentSourceSets`):

- **`src/main/`** — общий код (клиент + сервер). Точка входа: `org.mamoru.omnichat.Omnichat` (implements `ModInitializer`).
- **`src/client/`** — клиентский код. Точка входа: `org.mamoru.omnichat.client.OmnichatClient` (implements `ClientModInitializer`).

Mixin-конфигурации:
- `omnichat.mixins.json` — общие миксины, пакет `org.mamoru.omnichat.mixin`
- `omnichat.client.mixins.json` — клиентские миксины, пакет `org.mamoru.omnichat.mixin.client`

Метаданные мода определены в `src/main/resources/fabric.mod.json`. Версии зависимостей — в `gradle.properties`.

## Key Conventions

- Группа Maven: `org.mamoru`, artifact: `omnichat`
- Серверный код не должен попадать в `src/client/`, клиентский — не в `src/main/` (разделение environment source sets)
- Миксины требуют `@Overwrite` аннотации (`requireAnnotations: true`)
