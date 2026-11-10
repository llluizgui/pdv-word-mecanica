"""PDV Word Mecânica 1.9.6 — documentos A4 de OS e compartilhamento assistido."""
from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from base_app import connect
from os_documents_v196 import make_order_pdf, document_path, share_message, whatsapp_share_url
from ux_v195 import WorkspaceV195


class WorkspaceV196(WorkspaceV195):
    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica 1.9.6 | Siliro Tech')

    def make_orders(self):
        super().make_orders()
        actions = self._os_action_buttons
        actions['print'].configure(text='Imprimir OS • Entrada')
        actions['pdf'].configure(text='Imprimir serviço feito')
        bar = actions['print'].master
        self._os_send_buttons = {}
        for label, col, key, callback in (
            ('WhatsApp • OS', 0, 'share_os', lambda: self.alert(self.share_order_whatsapp)),
            ('WhatsApp • Final', 1, 'share_final', lambda: self.alert(self.share_completed_whatsapp)),
            ('Imprimir direto', 2, 'direct', lambda: self.alert(self.print_os_direct)),
            ('Abrir pasta PDFs', 3, 'folder', lambda: self.alert(self.open_os_documents_folder)),
        ):
            button=ttk.Button(bar,text=label,command=callback)
            button.grid(row=2,column=col,sticky='ew',padx=3,pady=3)
            self._os_send_buttons[key]=button
        self._os_pdf_notice=ttk.Label(
            self.os_selection_label.master,
            text='A OS abre em PDF para imprimir (Ctrl+P). Após concluir, gere a ficha final '
                 'com serviço realizado e fotos. Pelo WhatsApp, anexe o PDF manualmente.',
            foreground='#53687E',wraplength=900,justify='left')
        self._os_pdf_notice.pack(anchor='w',pady=(5,1))
        self._sync_os_actions()

    def _sync_os_actions(self,event=None):
        super()._sync_os_actions(event)
        if not hasattr(self,'_os_send_buttons'):
            return
        status=self._selected_status()
        selected=bool(status)
        self._os_send_buttons['share_os'].configure(
            state='normal' if selected else 'disabled')
        self._os_send_buttons['direct'].configure(
            state='normal' if selected else 'disabled')
        self._os_send_buttons['share_final'].configure(
            state='normal' if status=='Concluída' else 'disabled')
        self._os_send_buttons['folder'].configure(state='normal')

    def _make_os_pdf(self,osid,finished=False,destination=None):
        with connect() as con:
            return make_order_pdf(con,osid,finished=finished,destination=destination)

    def _open_pdf(self,path):
        """Abre no visualizador do Windows; Ctrl+P mostra a seleção de impressora."""
        path=Path(path)
        try:
            if os.name=='nt':
                os.startfile(str(path))
            elif not webbrowser.open(path.as_uri()):
                raise OSError('Não foi possível abrir o visualizador de PDF.')
        except (OSError, ValueError) as exc:
            # Arquivo preservado mesmo quando não existe associação de PDF instalada.
            messagebox.showwarning('PDF gerado — abra manualmente',
                f'O arquivo foi salvo em:\n{path}\n\n'
                f'O visualizador de PDF não abriu: {exc}\n'
                'Abra o arquivo com um leitor de PDF e pressione Ctrl+P.',
                parent=self)
        return path

    def print_os(self):
        """Imprime/reimprime a OS selecionada em PDF A4 (estado atual)."""
        osid=self._selected_order()
        path,_=self._make_os_pdf(osid)
        self._open_pdf(path)
        return path

    def print_final_os(self):
        """Gera a segunda ficha, só depois que o serviço estiver concluído."""
        osid=self._selected_order()
        return self._report_for(osid)

    def export_order_report(self):
        return self.print_final_os()

    def _report_for(self,osid):
        path,_=self._make_os_pdf(osid,finished=True)
        self._open_pdf(path)
        return path

    def print_os_direct(self):
        osid=self._selected_order()
        path,_=self._make_os_pdf(osid)
        if os.name=='nt':
            try:
                # A ação do Windows pode abrir um visualizador em vez de imprimir,
                # dependendo da associação de PDF no computador do cliente.
                os.startfile(str(path),'print')
                return path
            except (OSError,ValueError) as exc:
                messagebox.showwarning('Impressão direta indisponível',
                    f'O Windows não conseguiu enviar o PDF à impressora: {exc}\n'
                    'O PDF será aberto para você escolher a impressora (Ctrl+P).',
                    parent=self)
        self._open_pdf(path)
        return path

    def open_os_documents_folder(self):
        folder=document_path(1).parent
        try:
            if os.name=='nt':
                os.startfile(str(folder))
            elif not webbrowser.open(folder.as_uri()):
                raise OSError('Gerenciador de arquivos indisponível.')
        except (OSError,ValueError):
            messagebox.showinfo('Pasta dos PDFs',f'Os PDFs estão em:\n{folder}',parent=self)
        return folder

    def _share_os(self,finished=False):
        osid=self._selected_order()
        path,info=self._make_os_pdf(osid,finished=finished)
        message=share_message(osid,info,finished=finished)
        number=info['phone'] or ''
        if not messagebox.askyesno('Compartilhar OS pelo WhatsApp',
            f'PDF gerado:\n{path.name}\n\n'
            f'Cliente: {info["customer"]}\nWhatsApp cadastrado: {number or "não informado"}\n\n'
            'Vamos abrir o WhatsApp com a mensagem pronta e a pasta onde está o PDF.\n'
            'No WhatsApp clique no clipe, selecione Documento e escolha o PDF.\n\n'
            'O sistema NÃO enviará a mensagem nem anexará o arquivo sozinho. Continuar?',
            parent=self):
            return path
        # Copia o caminho para facilitar o anexo por seleção de arquivo.
        self.clipboard_clear()
        self.clipboard_append(str(path))
        self.update_idletasks()
        url=whatsapp_share_url(number,message)
        if not webbrowser.open(url):
            messagebox.showwarning('WhatsApp não abriu',
                'Não foi possível abrir o WhatsApp automaticamente. '
                f'Abra https://web.whatsapp.com e anexe:\n{path}',
                parent=self)
        # A pasta só precisa abrir no Windows, onde o instalador roda.
        if os.name=='nt':
            try:
                os.startfile(str(path.parent))
            except (OSError, ValueError):
                pass
        messagebox.showinfo('PDF para anexar',
            f'O PDF está salvo em:\n{path}\n\n'
            'Clique em Anexar → Documento no WhatsApp e escolha o arquivo. '
            'Revise o texto e envie você mesmo.\n'
            'O caminho do PDF também foi copiado.',
            parent=self)
        return path

    def share_order_whatsapp(self):
        return self._share_os(finished=False)

    def share_completed_whatsapp(self):
        return self._share_os(finished=True)
