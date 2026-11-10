# PDV Word Mecânica 1.9.0 — Avaliação

Sistema **independente do PDV Word Mercado**, para oficinas de carros e motos, desktop Windows e banco SQLite local.

## Atendimento unificado
1. Busque ou cadastre o cliente, uma única vez, com CPF/CNPJ, contato e endereço.
2. Selecione o veículo; caso só exista um vinculado, o programa o carrega automaticamente.
3. Descreva problema e mecânico, adicione peças do estoque **ou peças a comprar sem cadastro em estoque**, serviços e mão de obra.
4. Salve orçamento: **aguardando**. Se aprovado, cria uma OS e desconta apenas as peças efetivamente vinculadas ao estoque. Aprovação **não** significa pagamento.
5. Checklist com foto vinculada à mesma OS. É exigida foto para marcar OS como concluída.
6. Ao concluir, ofereça produtos extras do estoque, com venda vinculada ao mesmo cliente e à OS, ou receba o serviço no caixa.
7. Emita PDF de orçamento com logo e dados da loja e relatório final de serviço com fotos, pagamento registrado e produtos extras.

## Configuração inicial
- Pressione **Ctrl+A**, crie uma senha de pelo menos 8 caracteres e abra os relatórios.
- Em **Dados da oficina (PDFs)**, informe nome fantasia, razão social, CNPJ/CPF, endereço, cidade, WhatsApp, e-mail e logo JPG/PNG. Se estiver em branco, o cadastro é sugerido na primeira entrada protegida.
- A logo e os dados aparecerão nos novos PDFs de orçamento, vendas e relatório final.

## Banco e backups
Dados: `%LOCALAPPDATA%\PDVWordMecanica\mecanica.db`. Fotos: `%LOCALAPPDATA%\PDVWordMecanica\fotos`. Logo: `%LOCALAPPDATA%\PDVWordMecanica\marca`. Antes de atualizar, faça **cópia da pasta inteira** com o aplicativo fechado.

## Desenvolvimento e compilação
- Executar código: `python app.py` (Python 3.12, reportlab e pillow)
- Testar: `python test_workflow_v17.py`
- Compilar instalador: GitHub Actions `Gerar instalador Windows`. A versão usa PyInstaller onedir, sem UPX, e Inno Setup. Análise pontual do Defender no Windows runner é executada antes da publicação.

## Limitações de segurança e fiscal
Esta é uma **versão de avaliação** que ainda precisa de testes reais de instalação, fluxo de pagamento, migração e segurança antes de clientes comerciais. O programa **não emite NF-e, NFC-e ou NFS-e**, não faz TEF, não possui certificado de assinatura digital para o instalador. PDFs são **não fiscais**. Uma análise pontual sem detecção no CI **não garante** que o Windows do cliente não sinalize malware. Não desative o antivírus nem force instalação se houver detecção.

## Novidades 1.9.0
- Atendimento agora tem abas Cliente, Veículo, Orçamento, Peças e serviços, Finalizar e Histórico.
- Orçamentos **novos** somam valores não detalhados e itens, com desconto único; orçamentos antigos preservam a lógica original.
- Peças sem estoque podem ser lançadas manualmente no orçamento, sem baixar o inventário.
- Ordens de serviço filtráveis por mês, ano e status; no máximo 20 registros por página.
- Leitor de código de barras adiciona o item com Enter e atualiza imediatamente o total destacado no topo de Vendas.
- Após salvar o recebimento e criar o PDF, o caixa pergunta se deseja imprimir.
- Estoque tem campo Localização para corredor/prateleira/caixa.

**ATENÇÃO:** versão de avaliação, sem documentos fiscais. O instalador padrão continua sem assinatura digital; não desative mecanismos de segurança do Windows para instalá-lo. Salve uma cópia de `%LOCALAPPDATA%\\PDVWordMecanica` antes de atualizar.

## Correção 1.9.1 — ficha completa
O Atendimento voltou a exibir as seis seções no mesmo painel de rolagem, com atalhos para Cliente, Veículo, Orçamento, Peças e mão de obra, Finalizar e Histórico. Remove o Notebook interno que podia esconder as seções em algumas telas. Nenhum banco de dados é apagado nessa correção.

## Versão 1.9.2 — Scanner, agenda e filtros
- Leitor USB de teclado: no Caixa e Atendimento, reconhece SKU cadastrado mesmo que o campo de cliente esteja em foco. EAN-13 válido cadastrado pode entrar automaticamente sem Enter; códigos de outros tamanhos exigem Enter do scanner. O caixa soma cada leitura no carrinho e no valor a receber, com proteção de estoque e da OS. Tecla F8 posiciona o cursor na busca do produto.
- Atenção: os produtos precisam ter o código (SKU) cadastrado exatamente como o leitor envia. Teste em ambiente de avaliação antes de atender clientes.
- Ordens de serviço: mês, ano e situação independentes, com atalhos Hoje, Este mês, Todos, contadores por situação e paginação de 20 por tela.
- Agenda: ao selecionar e confirmar agendamento, abre nova ficha no Atendimento, preenchendo cliente, veículo, mecânico e descrição. Status vira Em atendimento. Nenhuma OS ou cobrança é gerada automaticamente.

## Versão 1.9.3 — Caixa compacto e scanner corrigido

- Caixa em painel compacto responsivo: cliente e busca de produto à esquerda; carrinho e pagamento à direita em telas largas, ou empilhados em telas menores. Total fixo no alto, sem banners e totais repetidos. A aba Financeiro/Despesas permanece disponível para preservar funções.
- Entrada por bipador, código manual, rótulo de seleção ou nome exato passa por validação de **ID de produto**, não só texto mostrado no campo. Enter/bipe = localizar e adicionar em uma ação, com atualização do total.
- Mantidas as regras de estoque, carrinho e OS: peça que já foi lançada na OS não pode entrar novamente na venda extra; a baixa física acontece só ao finalizar.
- Quantidade manual permanece ajustável; bipadas adicionam uma unidade por leitura.
- Este programa é uma avaliação sem emissão fiscal. Faça cópia de segurança do banco em \`%LOCALAPPDATA%\PDVWordMecanica\` antes de atualizar e teste o scanner físico do cliente.

## Versão 1.9.4 — OS compacta e semanal

- Redesenho da aba Ordens de Serviço no padrão visual do Caixa: orçamento e mecânico no topo, com botões Aprovar, Vincular aprovado, Iniciar, Concluir, Imprimir, Receber, Relatório final e Checklist agrupados.
- Campos técnicos antigos continuam disponíveis em **Detalhes opcionais**, sem ocupar a tela por padrão; "Vincular aprovado" somente para orçamento previamente aprovado, ainda sem OS.
- Abertura na semana atual (segunda a domingo). Semana anterior/próxima, Hoje, Esta semana, Todas, situação e filtros extras mês/ano. Histórico completo preservado, com 20 OS por página.
- Busca de nome, placa, número e data de nascimento do cliente, em formatos AAAA-MM-DD e DD/MM/AAAA, encontra OS em todo o histórico independentemente da semana selecionada.
- Resumo de uma OS selecionada e botões liberados pelo estado. A conclusão ainda exige fotos, por segurança.
- Corrigida impressão da OS que tentava ler "documento" do cadastro de mecânicos, coluna inexistente. Agora mostra especialidade.
- Somente a interface de ordens foi reorganizada; Caixa, Agenda, banco local, histórico e estoque continuam com as regras anteriores.

Faça backup da pasta \`%LOCALAPPDATA%\PDVWordMecanica\` antes de atualizar. Versão de avaliação, sem emissão de documento fiscal e ainda sem assinatura digital do instalador.

## PDV Mecânica 1.9.5 — conclusão comercial offline (funcionalidades 2, 4, 5, 6 e 8)

- **OS detalhada:** selecione uma OS aberta/em andamento, expanda **Detalhes opcionais**, edite previsão, defeito, diagnóstico, quilometragem, observações, garantia e custo estimado de mão de obra. Clique em **Salvar alterações da OS**. Registro de alterações com data; OS concluída/cancelada é somente leitura. Alteração de preço, quantidade de peças ou serviço já aprovado exige novo orçamento para não desalinhar estoque e cobranças.
- **Financeiro:** nova aba **Financeiro** com contas a pagar/receber, vencimento, status, pagamentos em parcelas até o saldo e baixa nos lançamentos do Caixa. OS concluídas podem ser recebidas em parcelas, reaproveitando o saldo de OS já existente; não há cobrança duplicada.
- **Estoque avançado:** encomendar peças do fornecedor, lista de compras pendentes, recebimento único por encomenda, custo médio ponderado, localização física, alertas de nível mínimo e margem unitária estimada. Encomendar não aumenta estoque nem gera despesa; o recebimento aumenta apenas uma vez. Registre a obrigação financeira à parte, quando houver pagamento ao fornecedor.
- **Aceite de orçamento:** botão na OS gera PDF comercial para enviar pelo WhatsApp manualmente ou imprimir e obter assinatura. Registre nome, canal e referência **real** da aprovação; somente então habilita Aprovar e abrir OS. O registro comprova uma declaração do operador e NÃO verifica assinatura eletrônica remotamente. Não existe link de aprovação remoto neste aplicativo offline.
- **Painel gerencial:** dentro da área protegida pelo Ctrl+A e senha, indicadores por período de recebimentos, despesas, OS, saldos, contas pendentes, estoque baixo, produtos mais vendidos, produtividade e margens brutas estimadas por OS; exportação HTML para impressão.
- **Interpretação financeira:** margens de OS usam custos ATUAIS das peças e custo de mão de obra declarado; não incluem impostos, aluguel, encargos nem custo histórico ausente, portanto **não são lucro líquido auditado**. O sistema permanece não fiscal. Backup recomendado: \`%LOCALAPPDATA%\PDVWordMecanica\` antes de instalar atualizações.


## PDV Mecânica 1.9.6 — OS para imprimir, enviar e reimprimir após o serviço

- **OS inicial em PDF A4:** abra **Ordens de serviço**, selecione a OS e clique em **Imprimir OS • Entrada**. O documento inclui dados da oficina, cliente, telefone, veículo, mecânico, situação, diagnóstico, peças/mão de obra, valores e campos de assinatura. Abre no visualizador padrão; use Ctrl+P para escolher a impressora. Há também **Imprimir direto** que usa o comando print do Windows quando suportado pela associação de PDF.
- **Ficha de serviço concluído:** depois de concluir a OS, selecione-a e clique em **Imprimir serviço feito**. Gera PDF A4 com descrição, diagnóstico, data de conclusão, peças/serviços, fotos de checklist (quando disponíveis), pagamentos recebidos, saldo e assinatura de entrega. Pode ser gerado quantas vezes forem necessárias, incluindo após novo pagamento parcial. Não gera a ficha final antes da conclusão.
- **WhatsApp:** botões **WhatsApp • OS** e **WhatsApp • Final** abrem a conversa do cliente com mensagem pronta, copiam o caminho do PDF e abrem a pasta dos documentos no Windows. O funcionário **anexa o PDF manualmente no WhatsApp** usando clipe → Documento e confirma o envio. O aplicativo offline não tem integração com a API WhatsApp para anexar e enviar automaticamente; a ação não prova envio ou entrega.
- Os PDFs ficam em %LOCALAPPDATA%\PDVWordMecanica\documentos, separados do banco local, e podem ser abertos novamente em **Abrir pasta PDFs**. Regerar o mesmo documento atualiza a cópia com o estado atual da OS, portanto o sistema não mantém uma versão imutável de cada emissão.
- **Impressão corrigida:** substitui o arquivo HTML temporário por PDF A4 com visualização e mensagens de fallback quando o Windows não possui leitor de PDF ou impressora associada. O documento não é fiscal.
- Faça backup de %LOCALAPPDATA%\PDVWordMecanica antes de instalar. O instalador continua sem assinatura digital.


## 1.9.7 — Diagnóstico de possível falso positivo no download

- Alternativa de empacotamento nativo **Nuitka --mode=standalone**, sem o bootloader do PyInstaller, mantendo o mesmo banco local e os mesmos fluxos da 1.9.6.
- Exige testes automatizados, inicialização do EXE resultante e varredura pontual do Defender no Windows do GitHub antes de liberar o Setup.
- **Não possui assinatura digital.** Uma compilação diferente não garante que Defender, SmartScreen ou o antivírus do cliente considerem o arquivo confiável, e não prova ausência de malware.
- Se aparecer **vírus detectado**, não desligue as proteções. Consulte Segurança do Windows → Histórico de proteção para identificar a ameaça e envie o nome da detecção. O arquivo poderá precisar ser enviado para análise da Microsoft como suspeita de falso positivo: https://www.microsoft.com/en-us/wdsi/filesubmission/.
