# PDV Word Mecânica — Siliro Tech

Aplicativo Windows exclusivo para oficinas mecânicas de carros e motos. Projeto **separado** do PDV Word de mercado.

## Versão 1.2.0 — testes de avaliação

### Melhorias
- Navegação compacta por módulos e rolagem vertical nas telas para uso em notebooks e monitores menores
- Cadastro rápido de cliente e veículo diretamente no orçamento
- Emissão de ficha técnica/orçamento em PDF e opção de imprimir no Windows
- Cadastro de peças, capacetes, GPS e acessórios no estoque
- Venda rápida de produtos com baixa automática no estoque, descontos e formas de pagamento
- Relatório de vendas por data, com itens e forma de pagamento; acesso com senha definida no primeiro uso
- Recebimentos de serviços e caixa separados das vendas de balcão no relatório

### Banco local e atualização
Os dados permanecem no PC em `%LOCALAPPDATA%\\PDVWordMecanica\\mecanica.db`, com fotos na pasta `fotos`. Faça backup do banco e da pasta de imagens antes de atualizar. As versões 1.1 e 1.2 utilizam o mesmo esquema, com migrações aditivas para os novos recursos.

### Instalador Windows
Acesse [Releases](https://github.com/llluizgui/pdv-word-mecanica/releases) e baixe `PDVWord_Mecanica_Setup_1.2.0.exe` da release 1.2.0 de avaliação quando a compilação terminar.

O computador que instala o aplicativo não precisa de Python.

### Aviso importante
**Não homologado para operação comercial definitiva.** Ainda não realiza NF-e/NFC-e/NFS-e, integração de TEF/maquininhas nem assinatura eletrônica verificável. A senha é específica para o acesso ao relatório; não é um sistema completo de permissões de usuários. Requer testes em computadores reais, validação de backups, de segurança e das integrações fiscais antes do uso em produção.

O compartilhamento pelo WhatsApp abre uma mensagem para revisão; a ficha PDF deve ser anexada manualmente.
