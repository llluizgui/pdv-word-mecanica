# PDV Word Mecânica 1.7 — Avaliação

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
