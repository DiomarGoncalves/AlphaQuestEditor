# Portabilidade e idiomas — Alpha Quest Editor 0.9

A 0.9 adiciona uma camada de compatibilidade para trabalhar com Quest Books SNBT e JSON5 no mesmo aplicativo.

## Formatos alvo

### Minecraft 1.21.1 / FTB Quests 2101.x
- Quest data: `.snbt`
- Idiomas: `lang/<locale>.snbt`
- Opcionalmente, idiomas podem estar divididos no layout do Quests Lang Splitter.

### Minecraft 26.1.2 / FTB Quests 26.1.2.x
- Quest data: `.json5`
- Idiomas: JSON5 separados por locale, tipo de objeto e capítulo.

## Converter SNBT → JSON5

1. Abra **Ferramentas → Conversor SNBT ↔ JSON5**.
2. Escolha o Quest Book ou a raiz do modpack de origem.
3. Selecione `SNBT 1.21.1 → JSON5 26.1.2` ou deixe em detecção automática.
4. Escolha uma pasta de saída diferente da origem.
5. Execute a conversão.
6. Leia os avisos do relatório.
7. Teste a cópia gerada no FTB Quests da versão de destino.

A conversão:
- cria `data.json5`;
- cria `chapter_groups.json5`;
- converte `chapters/*.snbt` para `chapters/*.json5`;
- converte reward tables quando presentes;
- organiza textos no layout de idiomas JSON5 separado;
- adiciona defaults necessários da linha 26.1.2 quando ausentes;
- preserva campos desconhecidos sempre que a representação é segura.

## Converter JSON5 → SNBT

O fluxo inverso permite portar um Quest Book de volta para a estrutura SNBT usada na linha 1.21.1.

Na conversão reversa você pode escolher gerar:
- idiomas SNBT flat; ou
- idiomas já separados no layout compatível com Quests Lang Splitter.

Campos exclusivos da versão nova podem não ter equivalente no FTB Quests antigo. Por isso, o editor mostra avisos e a cópia deve ser testada no jogo de destino.

## Lang Splitter

A aba **Lang Splitter** é voltada ao workflow 1.21.1/SNBT.

### Split

Exemplo de saída:

```text
lang/
├─ en_us/
│  ├─ chapters/
│  │  ├─ create_1.snbt
│  │  └─ create_2.snbt
│  ├─ chapter.snbt
│  ├─ chapter_group.snbt
│  ├─ file.snbt
│  └─ reward_table.snbt
└─ en_us.snbt
```

Quest, task, reward, quest link e image keys são associadas ao capítulo quando o editor consegue resolver o objeto dono.

### Merge

O editor também consegue recompor o arquivo flat a partir dos arquivos separados.

Antes de operações in-place, o Alpha Quest Editor cria backup do Quest Book.

## Tradução para IA

A aba **Traduções** continua permitindo exportar CSV/JSON. Um fluxo prático é:

1. filtrar somente textos ausentes;
2. exportar o relatório;
3. enviar o arquivo para a IA/tradutor sem alterar a coluna `key`;
4. importar o relatório traduzido;
5. revisar no Alpha Quest Editor;
6. salvar e validar.

A importação não usa campo vazio para apagar uma tradução já existente.

## Limites da alpha

O conversor não inicializa Minecraft/NeoForge nem executa o código dos mods. Ele converte estruturas de dados e aplica migrações que são seguras e conhecidas. Recursos muito específicos de uma versão devem ser revisados no FTB Quests de destino.

O objetivo é facilitar o port, não substituir o teste final dentro do jogo.
