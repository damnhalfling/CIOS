# CIOS — Rotina de Testes Manuais (RC58)

> Executar na máquina com CIOS instalado.
> Tempo estimado: 15-20 minutos.
> Anotar: ✅ passou | ❌ falhou (descrever)

---

## 1. Boot & Login (2 min)

| # | Teste | Esperado |
|---|-------|----------|
| 1.1 | Ligar a máquina | Plymouth splash (logo CIOS, sem texto) → greetd login |
| 1.2 | Fazer login | Transição suave → prompt CIOS aparece (bottom), topbar (top) |
| 1.3 | Topbar mostra info | Relógio, CPU, RAM, Wi-Fi status visíveis |
| 1.4 | Prompt aceita input | Cursor piscando, teclado funciona |

---

## 2. Intents Básicos — Sistema (3 min)

Digitar cada comando no prompt e verificar resposta:

| # | Input | Esperado |
|---|-------|----------|
| 2.1 | `quanta bateria` | Mostra % da bateria ou "AC power" |
| 2.2 | `qual o volume` | Mostra volume atual (ex: "75%") |
| 2.3 | `aumentar volume` | Volume sobe 10%, feedback visual |
| 2.4 | `silenciar` | Muta o áudio, confirma |
| 2.5 | `tirar o mute` | Desmuta, confirma |
| 2.6 | `meu computador tá lento` | Diagnóstico CPU/RAM, sugestões |
| 2.7 | `quanto de espaço` | Mostra disco livre/usado |

---

## 3. Wi-Fi (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 3.1 | `qual minha rede` | Mostra SSID conectado + IP |
| 3.2 | `listar redes` | Lista redes disponíveis com sinal |
| 3.3 | `conectar no wifi` | Se já conectado: "já conectado". Se não: lista redes |

---

## 4. Apps & Janelas (3 min)

| # | Input | Esperado |
|---|-------|----------|
| 4.1 | `abrir firefox` | Firefox abre (XWayland) |
| 4.2 | `abrir terminal` | foot terminal abre |
| 4.3 | `tile window left` | Janela ativa vai pra metade esquerda |
| 4.4 | Alt+Tab | Alterna entre janelas |
| 4.5 | Alt+F4 | Fecha janela ativa |
| 4.6 | Ctrl+Space | Overlay hotkey aparece |
| 4.7 | Ctrl+K | Search overlay aparece |
| 4.8 | Escape | Fecha overlay |

---

## 5. Execução de Comandos (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 5.1 | `run echo hello world` | Mostra "hello world" |
| 5.2 | `run ls /tmp` | Lista conteúdo de /tmp |
| 5.3 | `run rm -rf /` | BLOQUEADO — mensagem de segurança |
| 5.4 | `instalar htop` | Pede confirmação antes de instalar |

---

## 6. Fluxo Conversacional (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 6.1 | `conectar no wifi` | Pergunta "Qual rede?" (se não conectado) |
| 6.2 | Responder com nome da rede | Conecta ou tenta conectar |
| 6.3 | `desligar` | Pede confirmação ("Tem certeza?") |
| 6.4 | Responder "não" | Cancela, volta ao prompt |

---

## 7. Dev Workflow (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 7.1 | `quero trabalhar no projeto X` | Se existe: abre editor + server. Se não: cria |
| 7.2 | `mostrar os logs` | Mostra logs recentes do sistema |
| 7.3 | `o que posso fazer` | Lista categorias de capacidades |

---

## 8. Busca & Histórico (1 min)

| # | Input | Esperado |
|---|-------|----------|
| 8.1 | Ctrl+K → digitar "wifi" | Busca no histórico, mostra resultados |
| 8.2 | `busca no histórico sobre volume` | Retorna interações anteriores sobre volume |

---

## 9. Topbar & Indicadores (1 min)

| # | Teste | Esperado |
|---|-------|----------|
| 9.1 | Executar qualquer comando | Spinner aparece durante processamento |
| 9.2 | Após execução | Spinner desaparece, topbar volta ao normal |
| 9.3 | Se Ollama rodando | Indicador de IA visível na topbar |

---

## 10. Multi-Monitor (se disponível) (1 min)

| # | Teste | Esperado |
|---|-------|----------|
| 10.1 | Conectar monitor externo | Detectado automaticamente |
| 10.2 | `listar monitores` | Mostra monitores conectados |
| 10.3 | Janela no monitor secundário | Funciona normalmente |

---

## 11. Sessão & Shutdown (1 min)

| # | Input | Esperado |
|---|-------|----------|
| 11.1 | `suspender` | Máquina suspende |
| 11.2 | (acordar) | Volta ao estado anterior, prompt funcional |
| 11.3 | `bloquear` | Tela de lock aparece |
| 11.4 | Ctrl+Alt+F2 | VT switch funciona (TTY2) |
| 11.5 | Ctrl+Alt+F1 | Volta pro CIOS |

---

## 12. Resiliência (1 min)

| # | Teste | Esperado |
|---|-------|----------|
| 12.1 | Digitar lixo: `asdfghjkl` | "Não entendi" + sugestão de recovery |
| 12.2 | Input vazio (Enter) | Não crasha, ignora ou mensagem sutil |
| 12.3 | Input muito longo (200+ chars) | Processa sem crash |
| 12.4 | Fechar e reabrir terminal (foot) | CIOS continua rodando |

---

## Resultado

| Seção | Passou | Falhou | Notas |
|-------|--------|--------|-------|
| 1. Boot & Login | /4 | | |
| 2. Sistema | /7 | | |
| 3. Wi-Fi | /3 | | |
| 4. Apps & Janelas | /8 | | |
| 5. Execução | /4 | | |
| 6. Conversacional | /4 | | |
| 7. Dev Workflow | /3 | | |
| 8. Busca | /2 | | |
| 9. Topbar | /3 | | |
| 10. Multi-Monitor | /3 | | |
| 11. Sessão | /5 | | |
| 12. Resiliência | /4 | | |
| **TOTAL** | **/50** | | |

---

## Critérios de Aprovação

- **≥ 45/50 (90%):** RC aprovado para release
- **40-44 (80-89%):** Corrigir falhas antes de release
- **< 40 (< 80%):** Bloqueia release, investigar

---

*CIOS v2.0.0-rc58 — Maio 2026*
