import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawRightString(A4[0] - 40, 30, f"Страница {self._pageNumber} из {page_count}")
        self.drawString(40, 30, "FoodPorn & Old Money Manifestations — Confidential")
        self.restoreState()


def generate_order_pdf(order_id: int, customer_name: str, amount_uah: float, filename: str = None) -> str:
    if not filename:
        filename = f"storage/generated/order_{order_id}.pdf"

    os.makedirs(os.path.dirname(filename), exist_ok=True)

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#1A202C"),
        spaceAfter=15
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=16,
        textColor=colors.HexColor("#2D3748")
    )

    story = []
    story.append(Paragraph("<b>FOOD_PORN & OLD MONEY</b>", title_style))
    story.append(Paragraph("Электронный чек и спецификация заказа", body_style))
    story.append(Spacer(1, 15))

    data = [
        ["Номер заказа:", f"#{order_id}"],
        ["Клиент:", customer_name],
        ["Статус:", "Оплачено (PAID)"],
        ["Сумма оплаты:", f"{amount_uah:.2f} UAH"],
        ["Дата:", "Успешно проведено через Portmone"]
    ]

    t = Table(data, colWidths=[150, 350])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#2D3748")),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))

    story.append(t)
    story.append(Spacer(1, 25))
    story.append(Paragraph("Благодарим за сотрудничество! Ваша заявка передана в обработку.", body_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    return filename
