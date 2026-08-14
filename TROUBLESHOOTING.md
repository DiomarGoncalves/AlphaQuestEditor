# Troubleshooting

## A indexação parece pesada

Na v0.9.6.1 o scanner e os thumbnails trabalham fora da thread da interface. A primeira indexação após atualizar é intencionalmente nova porque o formato de cache mudou para `item_index_v6.json`.

Depois da primeira indexação, o cache é reaproveitado enquanto mods/KubeJS/resource packs não mudarem.

## Itens `minecraft:*` aparecem sem imagem

O Alpha precisa localizar o **JAR cliente** da versão do Minecraft para ler os modelos e texturas vanilla. Ele tenta automaticamente layouts do Launcher oficial, Prism Launcher e MultiMC.

Se o launcher usa uma estrutura diferente:

1. Abra **Ajuda**.
2. Clique em **Configurar JAR vanilla / texturas…**.
3. Selecione o JAR cliente da versão correta.
4. O Alpha fará uma reindexação forçada.

O arquivo correto deve conter `assets/minecraft/textures/item/` e `assets/minecraft/lang/en_us.json`.

## O Windows mostra "Não está respondendo"

Se ainda ocorrer na v0.9.6.1, abra **Ajuda → Copiar diagnóstico** e **Ajuda → Abrir pasta de logs** e envie o diagnóstico junto com o log mais recente.
