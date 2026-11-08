# PDV Word Mecânica 1.9 — avaliação Windows (offline)

A atualização preserva o banco SQLite existente em `%LOCALAPPDATA%\PDVWordMecanica\mecanica.db`. Não apague a pasta ao atualizar.

## Primeiro acesso

1. Instale/atualize e abra o aplicativo.
2. No primeiro acesso, cadastre o administrador **com login e senha pessoal de no mínimo 10 caracteres**; não há senha-padrão.
3. Use **Administração → Funcionários e permissões** para cadastrar operadores. O dono define individualmente quais módulos e ações cada funcionário pode usar.
4. Ao entrar, um operador autorizado recebe o convite para abrir o caixa. Informe o saldo inicial em dinheiro.
5. Depois, acesse **Caixa → Vendas**, selecione o cliente, a OS (se houver), o valor da entrada parcial ou total, os produtos extras, a forma de pagamento e o valor em dinheiro recebido, quando for o caso.
6. O sistema calcula o troco, emite um recibo A5 não fiscal, guarda o saldo restante da OS e registra as movimentações do turno.
7. Ao fechar o caixa, informe o dinheiro **contado na gaveta**. O aplicativo registra valor esperado, contado e diferença.

## Recursos adicionais

- **Backup automático:** no início e a cada hora de uso, faz uma cópia por dia em ZIP do banco/fotos/logo/assinaturas. No fechamento do caixa cria uma cópia extra. Por padrão usa `%LOCALAPPDATA%\PDVWordMecanica\backups_automaticos` (mesmo disco). Em **Administração → Pasta externa de backup** é possível configurar um destino externo, por exemplo pendrive ou pasta sincronizada.
- **Restauração:** somente o administrador restaura um ZIP ou banco antigo. Antes de substituir dados é criada uma cópia preventiva. Após restaurar, o programa fecha para aplicar mudanças de contas e senhas.
- **Estoque:** alerta ao entrar para itens com quantidade igual ou menor que o mínimo; lista também é mostrada no painel administrativo.
- **Assinatura:** após salvar o orçamento, ou na OS, o cliente pode desenhar a assinatura. Ela fica vinculada ao atendimento e entra nos PDFs. Uma assinatura manuscrita coletada em tela **não é uma assinatura digital qualificada**.
- **Contas:** papéis Administrador, Atendente, Caixa e Mecânico, com permissões individuais, bloqueio de operador e redefinição de senha pelo administrador. Usuários sem permissão não podem abrir/fechar caixa, registrar vendas, gerenciar estoque ou abrir relatórios.
- **Caixa:** um único turno aberto por banco local; dinheiro contabilizado por venda/recebimento líquido, entradas/saídas de dinheiro e suprimento/sangria autorizados. Pix e cartão não contam como dinheiro físico da gaveta.

## Limitações importantes

- Versão **de avaliação**. Não há emissão oficial de NF-e/NFC-e/NFS-e e nem TEF/homologação de maquininha. Orçamento e recibos são **documentos não fiscais**.
- Banco de dados local e backups não são criptografados. Restrinja o acesso à conta Windows, proteja pendrives/backups e evite pastas compartilhadas abertas. Permissões do aplicativo não substituem permissões do sistema operacional.
- O backup local no mesmo disco **não protege contra falha do computador**; configure destino externo.
- A primeira instalação em um PC não usa senha padrão. **Guarde a senha do administrador** em um local seguro. A versão não possui redefinição remota de senhas.
- Sempre faça backup antes de atualizar; teste a versão e o antivírus do Windows no seu próprio computador antes de distribuir ao cliente. Não desative proteções para instalar um aplicativo bloqueado.