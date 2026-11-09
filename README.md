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
