# CIOS — Security Boundary: OS vs Web

> Princípio arquitetural. Não negociável.

---

## Regra

**Execução é sempre local, nunca remota.**
**Sync é de conteúdo, nunca de capacidade.**
**Web é read-only sobre ações do OS.**

---

## Por quê

### 1. Segurança

Se execução estivesse na web:
- Acesso à conta = acesso ao hardware (instalar, deletar, desligar)
- Servidor precisaria de credenciais da máquina (SSH, sudo, tokens)
- Breach na API = controle total remoto do computador do usuário
- Superfície de ataque massiva (qualquer endpoint vira vetor)

Com a separação:
- Breach na web = vazamento de conversas (contido, sem acesso a hardware)
- Breach no OS = requer acesso físico à máquina
- Nenhum servidor tem credenciais de nenhuma máquina

### 2. Privacidade

- Comandos executados (apt install, wifi connect, arquivos movidos) ficam **apenas no OS**
- A web vê o registro textual ("instalou Chrome") mas não pode reproduzir a ação
- Dados sensíveis (senhas sudo, paths locais, configs) nunca saem da máquina
- O usuário controla o que sincroniza (opt-in, não opt-out)

### 3. Confiabilidade

- Execução local = zero latência de rede
- Funciona offline (skills, intent parser, Ollama)
- Sem dependência de disponibilidade de servidor para ações críticas
- Cloud down ≠ computador inutilizável

---

## O que cada camada faz

| Camada | Pode | Não pode |
|--------|------|----------|
| **Web (Intelligence)** | Conversar, gerar texto, acessar memória, ver histórico | Executar comandos, acessar filesystem, controlar hardware |
| **OS (CIOS)** | Tudo da web + executar, instalar, configurar, controlar | — |
| **Sync** | Transferir texto de conversas, memórias, metadata | Transferir credenciais, comandos executáveis, paths locais |

---

## Histórico unificado — regras

O histórico é uma timeline única que combina:
- **Ideias** (conversas da Intelligence, geração de texto) — sincroniza bidirecional
- **Comandos** (ações executadas no OS) — apenas local, web vê como registro read-only

### O que sincroniza (web ↔ OS)

- Texto das mensagens (user + assistant)
- Metadata cognitiva (tom, memória usada, honesty check)
- Artefatos gerados (textos, posts, código como texto)
- Títulos e clusters de conversas

### O que NÃO sincroniza (fica só no OS)

- Senhas (sudo, wifi)
- Paths absolutos do filesystem
- Output de comandos (stdout/stderr)
- Estado de tasks em background
- Credenciais de qualquer tipo

### O que a web vê sobre ações do OS

Registro textual sanitizado:
```
"14:30 — Instalou google-chrome-stable"
"14:32 — Conectou wifi Starlink"
"15:00 — Moveu 12 arquivos para Documentos"
```

Nunca:
```
"sudo apt-get install -y google-chrome-stable"  ← comando real
"/home/user/Downloads/*.pdf → /home/user/Documentos/"  ← paths reais
```

---

## Implicações para implementação

1. **Bridge** nunca expõe comandos raw para sync
2. **ThreadStore** marca turns como `local_only` quando contêm execução
3. **Sync payload** passa por sanitização antes de enviar
4. **Intelligence API** nunca recebe nem armazena credenciais do OS
5. **OS pode consumir** qualquer dado da web (conversas, memórias, artefatos)
6. **Web nunca consome** dados de execução do OS (só registros textuais)

---

## Resumo em uma frase

> A web é o cérebro que pensa. O OS é o corpo que age. O cérebro não precisa de mãos para ter ideias. Mas as mãos precisam do cérebro para saber o que fazer.

---

*Documentado: Maio 2026 — v2.0.0-rc14*
