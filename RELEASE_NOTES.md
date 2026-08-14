# Alpha Quest Editor v0.9.6.1-alpha

Esta é uma correção direta da v0.9.6-alpha para packs grandes no Windows.

## Corrigido

- Travamento/aparência de "Não está respondendo" ao terminar a indexação/cache.
- Leitura de thumbnails de itens fora da thread da interface.
- Catálogo inicial de itens muito pesado.
- Galeria de assets carregando imagens de forma síncrona.
- Detecção insuficiente do JAR cliente do Minecraft em Prism/MultiMC.
- Itens vanilla presentes na lista mas sem preview de textura quando o cliente Minecraft estava em um layout compartilhado do launcher.

## Novo fallback para texturas vanilla

Se o Alpha não localizar o JAR automaticamente, use:

`Ajuda → Configurar JAR vanilla / texturas…`

Escolha o JAR cliente da versão do Minecraft que contém `assets/minecraft/textures/item/` e o Alpha reindexará o projeto.

## Upgrade

A versão usa um novo cache de assets (`item_index_v6.json`). A primeira abertura pode fazer uma indexação nova; depois o cache volta a ser reutilizado.

O build Windows continua ONEFILE.
