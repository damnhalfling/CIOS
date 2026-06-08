# CIOS — Rotina de Testes Manuais (v3.0.0-rc14)

> Executar na máquina com CIOS instalado (ThinkPad E14 Gen 6).
> Tempo estimado: 40-50 minutos.
> Anotar: ✅ passou | ❌ falhou (descrever) | ⏭️ skip (não aplicável)

---

## 1. Boot & Login (2 min)

| # | Teste | Esperado |
|---|-------|----------|
| 1.1 | Ligar a máquina | Plymouth splash (logo CIOS, sem texto) → greetd login |
| 1.2 | Fazer login (user + senha) | Transição suave → compositor → prompt CIOS |
| 1.3 | Topbar visível | Relógio, CPU, RAM, Wi-Fi, battery, indicador IA |
| 1.4 | Prompt aceita input | Cursor piscando, teclado funciona |
| 1.5 | XDG dirs existem | ~/Desktop, ~/Downloads, ~/Documents criados |

---

## 2. Intents Básicos — Sistema (4 min)

| # | Input | Esperado |
|---|-------|----------|
| 2.1 | `quanta bateria` | % da bateria ou "AC power" |
| 2.2 | `qual o volume` | Volume atual (ex: "75%") |
| 2.3 | `aumentar volume` | +10%, feedback |
| 2.4 | `silenciar` | Muta áudio |
| 2.5 | `tirar o mute` | Desmuta |
| 2.6 | `meu computador tá lento` | Diagnóstico CPU/RAM/processos, sugestões |
| 2.7 | `quanto de espaço` | Disco livre/usado |
| 2.8 | `aumentar brilho` | Brilho sobe |
| 2.9 | `status do sistema` | Resumo geral (CPU, RAM, disco, uptime) |

---

## 3. Wi-Fi & Rede (3 min)

| # | Input | Esperado |
|---|-------|----------|
| 3.1 | `qual minha rede` | SSID conectado + IP |
| 3.2 | `listar redes` | Redes disponíveis com sinal % |
| 3.3 | `conectar no wifi` | Se conectado: confirma. Se não: lista opções |
| 3.4 | `meu ip` | Mostra IP local |

---

## 4. Bluetooth (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 4.1 | `bluetooth status` | Mostra se ligado/desligado |
| 4.2 | `ligar bluetooth` | Ativa BT (ou confirma que já está ligado) |
| 4.3 | `listar dispositivos bluetooth` | Lista devices pareados/disponíveis |

---

## 5. Apps & Janelas (4 min)

| # | Input / Ação | Esperado |
|---|-------|----------|
| 5.1 | `abrir firefox` | Firefox abre (XWayland) |
| 5.2 | `abrir terminal` | foot terminal abre |
| 5.3 | `tile window left` | Janela ativa → metade esquerda |
| 5.4 | `tile window right` | Janela ativa → metade direita |
| 5.5 | Alt+Tab | Alterna entre janelas |
| 5.6 | Alt+F4 | Fecha janela ativa |
| 5.7 | Ctrl+Space | Overlay aparece |
| 5.8 | Ctrl+K | Search overlay aparece |
| 5.9 | Escape | Fecha overlay |
| 5.10 | `fechar firefox` | Fecha processo do Firefox |

---

## 6. Execução de Comandos (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 6.1 | `run echo hello world` | Mostra "hello world" |
| 6.2 | `run ls /tmp` | Lista conteúdo |
| 6.3 | `run rm -rf /` | BLOQUEADO — mensagem de segurança |
| 6.4 | `run sudo rm -rf /home` | BLOQUEADO |
| 6.5 | `instalar htop` | Pede confirmação, instala se confirmar |

---

## 7. Fluxo Conversacional (3 min)

| # | Input | Esperado |
|---|-------|----------|
| 7.1 | `conectar no wifi` (se desconectado) | Pergunta "Qual rede?" |
| 7.2 | Responder com nome da rede | Conecta ou erro com sugestão |
| 7.3 | `desligar` | Pede confirmação |
| 7.4 | Responder "não" | Cancela, volta ao prompt |
| 7.5 | `o que posso fazer` | Lista categorias completa |
| 7.6 | `repete` / `como assim` | Usa contexto do turno anterior |

---

## 8. Dev Workflow (3 min)

| # | Input | Esperado |
|---|-------|----------|
| 8.1 | `quero trabalhar no projeto X` | Abre editor + server (ou cria) |
| 8.2 | `fechar o projeto` | Mata servidor, fecha janelas do projeto |
| 8.3 | `mostrar os logs` | Logs recentes do sistema |
| 8.4 | `clipboard history` | Mostra histórico de clipboard |

---

## 9. Arquivos & Disco (3 min)

| # | Input | Esperado |
|---|-------|----------|
| 9.1 | `onde está o arquivo X` | Busca por nome e conteúdo |
| 9.2 | `organizar meus downloads` | Organiza por tipo em subpastas |
| 9.3 | `libera espaço` | Analisa e sugere o que remover |
| 9.4 | `duplicatas na pasta X` | Encontra duplicatas (pHash + MD5) |
| 9.5 | `lixeira` | Mostra conteúdo da lixeira |

---

## 10. Galeria & Mídia (4 min)

| # | Input | Esperado |
|---|-------|----------|
| 10.1 | `minhas fotos` | Abre galeria |
| 10.2 | `fotos de ontem` | Filtra por data |
| 10.3 | `favoritar` (com foto aberta) | Marca como favorita |
| 10.4 | `criar álbum viagem` | Cria álbum |
| 10.5 | `print screen` | Screenshot (salva em ~/Pictures) |
| 10.6 | `gravar tela` | Inicia gravação |
| 10.7 | `parar gravação` | Para e salva |
| 10.8 | `girar foto` | Rotaciona 90° |
| 10.9 | `info da foto` | Mostra EXIF |

---

## 11. Theming & Display (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 11.1 | `modo escuro` | Alterna para dark mode |
| 11.2 | `modo claro` | Alterna para light mode |
| 11.3 | `night light` | Ativa filtro de luz azul |
| 11.4 | `resolução da tela` | Mostra resolução atual |
| 11.5 | `listar monitores` | Mostra monitores conectados |

---

## 12. VPN & Firewall (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 12.1 | `status vpn` | Mostra se conectado ou não |
| 12.2 | `conectar vpn` | Conecta (se configurado) ou orienta |
| 12.3 | `status firewall` | Mostra regras ativas |
| 12.4 | `bloquear porta 8080` | Adiciona regra ufw |

---

## 13. Scheduler & Automações (2 min)

| # | Input | Esperado |
|---|-------|----------|
| 13.1 | `me lembra às 17h de sair` | Agenda reminder |
| 13.2 | `listar lembretes` | Mostra agendados |
| 13.3 | `cancelar lembrete` | Remove |

---

## 14. Automount & Periféricos (2 min)

| # | Teste | Esperado |
|---|-------|----------|
| 14.1 | Plugar USB drive | Notificação de device detectado, monta |
| 14.2 | `listar devices` | Mostra USB/drives montados |
| 14.3 | `ejetar usb` | Desmonta com segurança |

---

## 15. Google Workspace (3 min, requer login Intelligence)

| # | Input | Esperado |
|---|-------|----------|
| 15.1 | `meus emails` | Lista emails recentes (Gmail) |
| 15.2 | `minha agenda` | Mostra eventos do dia (Calendar) |
| 15.3 | `meu dia` / `daily briefing` | Briefing completo (reuniões + emails + foco) |

---

## 16. Intelligence — Chat Cloud (3 min, requer login)

| # | Input | Esperado |
|---|-------|----------|
| 16.1 | Login via sidebar ("Entrar com Google") | Browser abre, OAuth, token salvo |
| 16.2 | `o que aconteceu hoje no mundo` | Consultando Intelligence → resumo |
| 16.3 | Resposta com streaming | Tokens aparecem progressivamente |
| 16.4 | `qual sua opinião sobre X` | Posiciona com justificativa (OpinionLayer) |
| 16.5 | `você é uma IA?` | Confirma transparentemente (IdentityShield) |
| 16.6 | Bater limite diário (free=5) | Mensagem clara + sugestão upgrade |

---

## 17. Cross-Device (2 min, requer Puccini ou Web)

| # | Teste | Esperado |
|---|-------|----------|
| 17.1 | Enviar comando do mobile → OS | Notificação aparece no OS |
| 17.2 | Confirmar execução | Comando executado, status reportado |
| 17.3 | Comando write sem confirmação | Fica pending (não executa automaticamente) |

---

## 18. Busca & Histórico (2 min)

| # | Input / Ação | Esperado |
|---|-------|----------|
| 18.1 | Ctrl+K → digitar "wifi" | Busca no histórico, resultados relevantes |
| 18.2 | `busca no histórico sobre volume` | Retorna interações anteriores |
| 18.3 | Ctrl+K → Enter num resultado | Abre/exibe detalhes |

---

## 19. Topbar & Indicadores (1 min)

| # | Teste | Esperado |
|---|-------|----------|
| 19.1 | Executar comando | Spinner aparece |
| 19.2 | Após execução | Spinner desaparece |
| 19.3 | Ollama rodando | Indicador IA visível |
| 19.4 | Intelligence logado | Nome/foto na sidebar |

---

## 20. Multi-Monitor (2 min, se disponível)

| # | Teste | Esperado |
|---|-------|----------|
| 20.1 | Conectar monitor externo | Detectado automaticamente |
| 20.2 | `listar monitores` | Mostra ambos |
| 20.3 | Janela no monitor secundário | Funciona, decorações presentes |
| 20.4 | `arranjar monitores` | Intent reconhecido |

---

## 21. Sessão & Power (2 min)

| # | Input / Ação | Esperado |
|---|-------|----------|
| 21.1 | `suspender` | Máquina suspende |
| 21.2 | Acordar (lid open / tecla) | Volta ao estado anterior |
| 21.3 | `bloquear` | Tela de lock (greetd) |
| 21.4 | Ctrl+Alt+F2 | VT switch → TTY2 |
| 21.5 | Ctrl+Alt+F1 | Volta pro CIOS |
| 21.6 | `logout` | Volta pra tela de login |

---

## 22. Resiliência & Edge Cases (2 min)

| # | Teste | Esperado |
|---|-------|----------|
| 22.1 | Digitar lixo: `asdfghjkl` | "Não entendi" + sugestão |
| 22.2 | Input vazio (Enter) | Não crasha |
| 22.3 | Input muito longo (500 chars) | Processa ou trunca sem crash |
| 22.4 | Fechar e reabrir terminal | CIOS continua rodando |
| 22.5 | Matar Ollama (`pkill ollama`) | Graceful degradation (regex still works) |
| 22.6 | Desconectar Wi-Fi | Skills locais continuam, Intelligence mostra "offline" |
| 22.7 | Reconectar Wi-Fi | Intelligence volta automaticamente |

---

## 23. Trash / Lixeira (1 min)

| # | Input | Esperado |
|---|-------|----------|
| 23.1 | `mover arquivo pra lixeira` | Move (soft delete) |
| 23.2 | `ver lixeira` | Lista itens |
| 23.3 | `esvaziar lixeira` | Pede confirmação antes de deletar |

---

## 24. Keyring & Secrets (1 min)

| # | Teste | Esperado |
|---|-------|----------|
| 24.1 | App que usa gnome-keyring | Secrets armazenados sem erro |
| 24.2 | `listar senhas salvas` | Mostra keys (sem valores) ou orienta |

---

## 25. Backup & Locale (1 min)

| # | Input | Esperado |
|---|-------|----------|
| 25.1 | `idioma do sistema` | Mostra locale atual |
| 25.2 | `fuso horário` | Mostra timezone |
| 25.3 | `backup` | Inicia ou orienta sobre backup |

---

---

## Resultado

| Seção | Total | Passou | Falhou | Notas |
|-------|-------|--------|--------|-------|
| 1. Boot & Login | 5 | | | |
| 2. Sistema | 9 | | | |
| 3. Wi-Fi & Rede | 4 | | | |
| 4. Bluetooth | 3 | | | |
| 5. Apps & Janelas | 10 | | | |
| 6. Execução | 5 | | | |
| 7. Conversacional | 6 | | | |
| 8. Dev Workflow | 4 | | | |
| 9. Arquivos & Disco | 5 | | | |
| 10. Galeria & Mídia | 9 | | | |
| 11. Theming & Display | 5 | | | |
| 12. VPN & Firewall | 4 | | | |
| 13. Scheduler | 3 | | | |
| 14. Automount | 3 | | | |
| 15. Google Workspace | 3 | | | |
| 16. Intelligence | 6 | | | |
| 17. Cross-Device | 3 | | | |
| 18. Busca | 3 | | | |
| 19. Topbar | 4 | | | |
| 20. Multi-Monitor | 4 | | | |
| 21. Sessão & Power | 6 | | | |
| 22. Resiliência | 7 | | | |
| 23. Trash | 3 | | | |
| 24. Keyring | 2 | | | |
| 25. Backup & Locale | 3 | | | |
| **TOTAL** | **119** | | | |

---

## Critérios de Aprovação

- **≥ 107/119 (90%):** Aprovado para release
- **95-106 (80-89%):** Corrigir falhas críticas antes de release
- **< 95 (< 80%):** Bloqueia release

## Notas

- Seções 15-17 requerem login Intelligence (skip se não configurado)
- Seção 14 requer USB drive físico (skip se não disponível)
- Seção 20 requer monitor externo (skip se não disponível)
- Seções skip não contam no total para critério de aprovação

---

*CIOS v3.0.0-rc14 — Junho 2026*
