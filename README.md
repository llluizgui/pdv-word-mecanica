# PDV Word Mecânica — v1.3.0 (avaliação)

Sistema local e independente do PDV Word original, voltado a oficinas de carros e motos.

## Novidades 1.3

- **Orçamentos:** botões Aprovar e Rejeitar. Aguardando aprovação é o estado inicial. Ao aprovar, o sistema cria uma única OS vinculada ao cliente e veículo, com mecânico selecionado, itens e estoque. Rejeitar mantém histórico, sem movimentar o caixa. Não é possível aprovar a mesma OS duas vezes.
- **OS e checklist:** seleção da OS mostra cliente, placa, serviço e mecânico. Fotos de entrada/saída são copiadas para a pasta local de dados da oficina.
- **Caixa:** pesquise nome do cliente, placa, número da OS, nome/código do produto. OS preenche descrição e **saldo restante**; produto encaminha à Venda rápida. Recebimentos parciais são permitidos, mas não acima do valor da OS.
- **Relatórios:** `Ctrl+A` de qualquer tela abre módulo protegido por senha criada no primeiro acesso. Filtros Hoje/Semana/Mês/Ano ou datas personalizadas, com vendas, forma de pagamento, receitas, despesas, saldo, OS e orçamentos por situação. Os valores de orçamentos aprovados aparecem no **total a receber**, mas **não** como entrada de caixa até o pagamento efetivo.
- **Documentos:** PDF do orçamento e comprovante PDF **NÃO FISCAL** do pagamento. O envio ao WhatsApp exige anexar o PDF manualmente.
- **Dados:** migração aditiva preserva banco em `%LOCALAPPDATA%\PDVWordMecanica\mecanica.db` nas atualizações. Fotos em `%LOCALAPPDATA%\PDVWordMecanica\fotos\`. Faça backup antes de atualizar e mantenha os arquivos de fotos.

## Windows

No GitHub, abra a versão `v1.3.0-avaliacao` em **Releases** e baixe `PDVWord_Mecanica_Setup_1.3.0.exe`, após a compilação com status de sucesso. Windows 10/11 64 bits. O computador do cliente **não** precisa de Python.

## Importante antes de uso comercial

**Software em avaliação:** ainda sem integração com SEFAZ/NFS-e, NF-e/NFC-e, TEF ou adquirentes, autenticação de todos os operadores, trilha de auditoria completa, conciliação bancária e testes de aceitação em computador do cliente. O comprovante PDF **não substitui nota fiscal**. Não insira dados reais de clientes nem use para operações fiscais até validar obrigações legais e integridade do backup/restauração. É aconselhável orientar-se com o contador da oficina.

## Construir localmente (desenvolvimento)

No Windows, com Python 3.12 e Inno Setup 6:

```bat
pip install pyinstaller==6.16.0 reportlab==4.4.9
GERAR_INSTALADOR_WINDOWS.bat
```

Código próprio em repositório separado. Nenhuma dependência do PDV Word Mercado.
