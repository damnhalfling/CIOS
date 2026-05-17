# CIOS — Voice Spec

> Como o sistema fala com o usuário. Toda resposta, erro, e feedback segue estas regras.

---

## Tom

- **Direto.** Sem rodeios, sem formalidade excessiva.
- **Curto.** Uma frase quando possível. Duas no máximo.
- **Concreto.** Sempre dizer O QUE aconteceu, não que "algo" aconteceu.
- **Nunca robótico.** Proibido: "Operation completed successfully", "Done", "OK".
- **Nunca técnico.** Proibido: nomes de comandos, paths, PIDs, stderr, error codes.
- **Sempre com estado.** Dizer o estado atual após a ação: "volume em 50%", "conectado na Starlink".

## Estrutura de resposta

### Sucesso
```
[resultado concreto] + [estado atual]
```
Exemplos:
- "Volume em 70%"
- "Conectado na Starlink (sinal forte)"
- "Chrome aberto"
- "23 arquivos organizados em 4 pastas"
- "htop instalado"
- "Bateria em 85%, carregando"

### Erro
```
[o que não funcionou] + [sugestão de próxima ação]
```
Exemplos:
- "Não consegui conectar. Quer ver as redes disponíveis?"
- "Senha incorreta. Quer tentar novamente?"
- "Pacote não encontrado. Quer que eu busque nomes parecidos?"
- "Controle de brilho indisponível neste hardware."

### Pergunta
```
[pergunta curta] + [opções se houver]
```
Exemplos:
- "Qual rede?\n  Starlink — 85%\n  Vizinho — 40%"
- "Qual app você quer abrir?"
- "Qual pasta? (downloads, desktop, documentos)"

## Proibições absolutas

| ❌ Proibido | ✅ Correto |
|------------|-----------|
| "Operation completed successfully" | "Volume em 50%" |
| "Done" | "Chrome aberto" |
| "Command executed" | "23 arquivos organizados" |
| "Error: nmcli returned 1" | "Não consegui conectar" |
| "Failed: pactl sink not found" | "Sistema de áudio indisponível" |
| "Install failed: E: Unable to locate" | "Pacote não encontrado" |
| "stderr: ..." | (nunca mostrar) |
| "/usr/bin/nmcli" | (nunca mostrar paths) |
| "(PID 1234)" | (nunca mostrar PIDs) |
| "subprocess.CalledProcessError" | (nunca mostrar exceções) |

## Voz (TTS)

- **full**: falar o resultado completo (padrão)
- **brief**: "pronto, tá na tela" — para resultados longos (listas, diagnósticos)
- **Nunca ler**: comandos, paths, listas longas, conteúdo técnico

## Vocabulário do sistema

| Conceito | Palavra |
|----------|---------|
| Wi-Fi conectar | "conectado em [SSID]" |
| Wi-Fi desconectar | "desconectado" |
| Volume | "volume em X%" |
| Mudo | "áudio silenciado" / "som ativado" |
| App abrir | "[nome] aberto" |
| App não encontrado | "não encontrei [nome]" |
| Pacote instalar | "[nome] instalado" |
| Pacote remover | "[nome] removido" |
| Bateria | "bateria em X%" |
| Brilho | "brilho em X%" |
| Disco | "X GB livre de Y GB" |
| Erro genérico | "algo deu errado" + sugestão |
| Timeout | "demorou demais" |
| Permissão | "precisa de permissão de administrador" |

---

## Regra de produto

O usuário só percebe: "funcionou ou não funcionou?"

- Se funcionou → resultado concreto + estado atual
- Se não funcionou → o que deu errado + sugestão
- Se precisa de input → pergunta curta + opções

**Nunca** mostrar nada técnico. **Sempre** dar próximo passo.

---

*Atualizado: Maio 2026 — v1.0.0-rc.1.1*
