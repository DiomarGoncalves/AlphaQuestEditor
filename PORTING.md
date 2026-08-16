# Portabilidade e idiomas — Alpha Quest Editor 0.9.8

## Port Universal — matriz de versões

A ferramenta **Port** na navbar agora escolhe rotas por geração do FTB Quests, em vez de exigir que o usuário combine manualmente migração de lang e conversão de storage.

| Origem | Destino | Rota |
|---|---|---|
| 1.20.x | 1.21.x | SNBT inline → SNBT + `lang/<locale>.snbt` |
| 1.20.x | 26.1.2 | Pipeline direto; etapa 1.21 temporária + JSON5 |
| 1.20.x | 1.21.x → 26.1.2 | Igual ao pipeline direto, mas preserva a cópia intermediária 1.21 |
| 1.21.x | 26.1.2 | SNBT → JSON5 + lang dividido |
| 26.1.2 | 1.21.x | JSON5 → SNBT + lang externo |
| 1.21.x | 1.20.x | Backport de um locale para texto inline |

A origem nunca é alterada. A rota direta 1.20 → 26.1.2 usa a mesma migração conservadora 1.20 → 1.21 em uma pasta temporária e só então gera JSON5; dessa forma as traduções passam pela etapa apropriada sem duplicar lógica.

A 0.9 adiciona uma camada de compatibilidade para trabalhar com Quest Books SNBT e JSON5 no mesmo aplicativo.

## Formatos alvo

### Minecraft 1.21.1 / FTB Quests 2101.x
- Quest data: `.snbt`
- Idiomas: `lang/<locale>.snbt`
- Opcionalmente, idiomas podem estar divididos no layout do Quests Lang Splitter.

### Minecraft 26.1.2 / FTB Quests 26.1.2.x
- Quest data: `.json5`
- Idiomas: JSON5 separados por locale, tipo de objeto e capítulo.

## Portar FTB Quests 1.20.x ↔ 1.21.x

A aba **FTB 1.20 ↔ 1.21** trata uma mudança diferente do conversor SNBT/JSON5: as duas famílias continuam usando SNBT, mas o sistema de textos traduzíveis mudou.

### 1.20.x → 1.21.x

1. Abra **Port** na navbar (ou **Converter → FTB 1.20 ↔ 1.21**).
2. Escolha a pasta do Quest Book antigo.
3. Use **Analisar origem** para conferir quests, textos inline, conflitos e ItemStacks com NBT legado.
4. Escolha o locale de destino (normalmente `en_us`).
5. Escolha uma pasta de saída diferente.
6. Execute **Portar agora**.

O Alpha move para `lang/<locale>.snbt` os textos conhecidos de file, chapter groups, reward tables, chapters, quests, tasks, rewards e quest links. Títulos/subtítulos/descrições com IDs válidos são removidos da estrutura somente na cópia gerada.

Se a origem já possuir um `lang/<locale>.snbt`, valores externos deliberados são preservados e vencem o texto inline em caso de conflito.

### 1.21.x → 1.20.x

O fluxo inverso escolhe um locale e volta a embutir seus textos nos objetos SNBT. Como o formato antigo não oferece o mesmo modelo externo para múltiplos idiomas, apenas o locale selecionado pode ser materializado no Quest Book de destino. Por padrão a pasta `lang/` é removida da cópia de backport.

### Segurança do port

- A origem nunca é alterada.
- Projetos mistos/parcialmente migrados exigem que a direção seja escolhida explicitamente.
- Objetos com texto mas sem ID seguro são preservados inline.
- NBT customizado de ItemStacks é preservado, mas não é reescrito automaticamente como componentes da versão nova.
- O relatório final avisa sobre conteúdo que merece revisão no jogo.

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
