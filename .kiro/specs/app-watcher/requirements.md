# Documento de Requisitos

## Introdução

Quando o usuário instala um novo aplicativo (via `dpkg -i`, `apt install`, Flatpak, etc.), o cache do `app_launcher` do CIOS não se atualiza até que a sessão seja reiniciada. Isso causa falhas como "não encontrado" ao tentar abrir um app recém-instalado por voz. Esta feature implementa um watcher reativo usando inotify que monitora os diretórios de `.desktop` files e invalida/reconstrói automaticamente o cache quando mudanças são detectadas, seguindo o mesmo padrão dos watchers existentes no MCP (wifi, áudio, bluetooth).

## Glossário

- **App_Watcher**: Componente reativo que monitora diretórios de arquivos `.desktop` via inotify e notifica o sistema sobre mudanças (criação, modificação, remoção de arquivos `.desktop`).
- **App_Launcher**: Módulo existente (`app_launcher.py`) responsável por escanear arquivos `.desktop`, construir o cache de aplicativos instalados e localizar/iniciar aplicativos por nome.
- **MCP**: Model Context Protocol — módulo central (`mcp.py`) que mantém o estado vivo do sistema via polling adaptativo e watchers reativos.
- **Cache_De_Apps**: Lista em memória de objetos `AppInfo` construída a partir dos arquivos `.desktop` encontrados nos diretórios monitorados.
- **Debounce**: Técnica que agrupa múltiplos eventos rápidos em uma única ação, esperando um período de silêncio antes de executar.
- **Período_De_Silêncio**: Intervalo de 2 segundos sem novos eventos de filesystem antes de disparar o rescan.
- **Diretórios_Monitorados**: Os caminhos `/usr/share/applications/` e `~/.local/share/applications/` onde arquivos `.desktop` são instalados.
- **Evento_De_Desktop_File**: Criação, modificação ou remoção de um arquivo com extensão `.desktop` dentro dos Diretórios_Monitorados.

## Requisitos

### Requisito 1: Monitoramento de Diretórios via Inotify

**User Story:** Como usuário do CIOS, eu quero que o sistema detecte automaticamente quando novos aplicativos são instalados, para que eu possa abri-los por voz imediatamente sem reiniciar a sessão.

#### Critérios de Aceitação

1. WHEN o MCP inicia, THE App_Watcher SHALL começar a monitorar os Diretórios_Monitorados para eventos de criação, modificação e remoção de arquivos.
2. WHEN um Evento_De_Desktop_File ocorre em `/usr/share/applications/`, THE App_Watcher SHALL detectar o evento.
3. WHEN um Evento_De_Desktop_File ocorre em `~/.local/share/applications/`, THE App_Watcher SHALL detectar o evento.
4. IF um dos Diretórios_Monitorados não existir no momento da inicialização, THEN THE App_Watcher SHALL ignorar esse diretório e monitorar os demais sem erro.
5. THE App_Watcher SHALL filtrar eventos para processar apenas arquivos com extensão `.desktop`.

### Requisito 2: Debounce de Eventos

**User Story:** Como desenvolvedor do CIOS, eu quero que múltiplos eventos de filesystem sejam agrupados antes de disparar um rescan, para que instalações de pacotes com muitos `.desktop` files não causem rescans excessivos.

#### Critérios de Aceitação

1. WHEN um Evento_De_Desktop_File é detectado, THE App_Watcher SHALL iniciar um temporizador de Período_De_Silêncio de 2 segundos.
2. WHEN outro Evento_De_Desktop_File é detectado durante um Período_De_Silêncio ativo, THE App_Watcher SHALL reiniciar o temporizador para 2 segundos.
3. WHEN o Período_De_Silêncio expira sem novos eventos, THE App_Watcher SHALL disparar exatamente um rescan do Cache_De_Apps.
4. WHILE o temporizador de debounce estiver ativo, THE App_Watcher SHALL continuar aceitando novos eventos sem disparar rescans intermediários.

### Requisito 3: Invalidação e Reconstrução do Cache

**User Story:** Como usuário do CIOS, eu quero que o cache de aplicativos seja atualizado automaticamente após mudanças detectadas, para que a busca por apps sempre retorne resultados atualizados.

#### Critérios de Aceitação

1. WHEN o debounce expira e o rescan é disparado, THE App_Watcher SHALL chamar a função de invalidação do Cache_De_Apps.
2. WHEN a invalidação é executada, THE App_Launcher SHALL reconstruir o Cache_De_Apps escaneando todos os diretórios de `.desktop` files na próxima consulta.
3. THE App_Launcher SHALL manter o cache anterior acessível para consultas que estejam em andamento durante a reconstrução.

### Requisito 4: Inicialização com o MCP

**User Story:** Como desenvolvedor do CIOS, eu quero que o App_Watcher seja iniciado como parte do ciclo de vida do MCP, para que o monitoramento esteja ativo durante toda a sessão do usuário.

#### Critérios de Aceitação

1. WHEN o método `start()` do MCP é chamado, THE App_Watcher SHALL ser iniciado após a conclusão do warmup paralelo.
2. WHEN o método `stop()` do MCP é chamado, THE App_Watcher SHALL encerrar o monitoramento e liberar recursos de inotify.
3. THE App_Watcher SHALL executar em uma thread daemon dedicada, sem bloquear a inicialização do MCP.
4. IF o App_Watcher falhar durante a inicialização, THEN THE MCP SHALL registrar um log de warning e continuar operando normalmente sem monitoramento de apps.

### Requisito 5: Thread Safety na Invalidação do Cache

**User Story:** Como desenvolvedor do CIOS, eu quero que a invalidação e reconstrução do cache seja thread-safe, para que chamadas concorrentes ao app_launcher de qualquer thread não causem race conditions.

#### Critérios de Aceitação

1. THE App_Launcher SHALL utilizar um mecanismo de lock para proteger operações de leitura e escrita no Cache_De_Apps.
2. WHILE o Cache_De_Apps estiver sendo reconstruído, THE App_Launcher SHALL permitir leituras concorrentes usando o cache anterior.
3. WHEN múltiplas invalidações são solicitadas simultaneamente, THE App_Launcher SHALL executar apenas um rescan e descartar solicitações redundantes.

### Requisito 6: Sem Dependências Externas Adicionais

**User Story:** Como desenvolvedor do CIOS, eu quero que a implementação use apenas bibliotecas já disponíveis no projeto, para evitar adicionar dependências ao sistema.

#### Critérios de Aceitação

1. THE App_Watcher SHALL utilizar uma das seguintes opções para monitoramento de filesystem: `inotify_simple`, inotify via `ctypes`, ou `GLib.FileMonitor` (disponível via GTK4).
2. THE App_Watcher SHALL não introduzir pacotes Python que não estejam já instalados no ambiente de execução do CIOS.
