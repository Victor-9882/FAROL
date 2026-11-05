"""Modelos da Aplicação Core.

Seguem o Diagrama de Classes e o DER do Relatório Descritivo (Seções 1.4 e 1.5),
com estas mudanças, a registrar numa Solicitação de Mudança do DER:

- `HistoricoTurma`: o DER não guarda o histórico de turmas exigido pela RN011
  (achado da revisão estática do Plano de Testes).
- `Intervencao.aluno`: o DER liga a intervenção só ao alerta, mas o RF019 admite
  intervenção sem alerta associado.
- `ResultadoSimulado.presente`: registra a ausência no simulado (RN009).
- `ResultadoRedacao`: as notas por competência viram cinco colunas (c1 a c5), e
  o tema é identificado pela terça-feira em que foi lançado (RN007).
"""

from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models import Q

from .historico import HistoricoPreservado


class Usuario(AbstractUser):
    """Membro da gestão do CASD que acessa o FAROL (RF001, RF002).

    O perfil define o que é exibido: só o Diretor vê dados nominais (RN013, NF013).
    O padrão é Membro, o perfil mais restrito.
    """

    class Perfil(models.TextChoices):
        DIRETOR = "DIRETOR", "Diretor"
        MEMBRO = "MEMBRO", "Membro de diretoria"

    email = models.EmailField("e-mail", unique=True)
    perfil = models.CharField(max_length=10, choices=Perfil.choices, default=Perfil.MEMBRO)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    @property
    def is_diretor(self) -> bool:
        return self.perfil == self.Perfil.DIRETOR


# --- Gestão de Alunos ----------------------------------------------------------------


class Turma(HistoricoPreservado):
    """Turma de um ano letivo. A divisão dos alunos é aleatória (RN011)."""

    nome = models.CharField(max_length=60)
    ano = models.PositiveSmallIntegerField("ano letivo")

    class Meta:
        verbose_name = "turma"
        verbose_name_plural = "turmas"
        ordering = ["-ano", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["nome", "ano"], name="turma_unica_por_ano"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.ano})"


class Aluno(HistoricoPreservado):
    """Aluno do CASDvest, identificado unicamente pela matrícula (RN003).

    `turma` é a turma atual. Para trocar de turma use `mudar_turma()`, que
    preserva o histórico (RN011).
    """

    matricula = models.CharField("matrícula", max_length=20, primary_key=True)
    nome = models.CharField(max_length=150)
    data_ingresso = models.DateField(
        "data de ingresso",
        help_text="Há várias chamadas de matrícula no ano; o aluno entra nos indicadores "
        "a partir desta data (RN004).",
    )
    turma = models.ForeignKey(
        Turma, on_delete=models.PROTECT, related_name="alunos", verbose_name="turma atual"
    )

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"
        ordering = ["nome"]
        constraints = [
            models.CheckConstraint(condition=~Q(matricula=""), name="aluno_matricula_preenchida"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.matricula})"

    def save(self, *args, **kwargs):
        novo = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if novo:
                HistoricoTurma.objects.create(
                    aluno=self, turma=self.turma, data_inicio=self.data_ingresso
                )

    @transaction.atomic
    def mudar_turma(self, nova_turma: Turma, data):
        """Move o aluno para `nova_turma` a partir de `data`, preservando o histórico (RN011)."""
        if nova_turma.pk == self.turma_id:
            return
        atual = self.historico_turmas.get(data_fim__isnull=True)
        if data <= atual.data_inicio:
            raise ValueError("A mudança de turma deve ser posterior ao início da turma atual.")
        atual.data_fim = data
        atual.save(update_fields=["data_fim"])
        HistoricoTurma.objects.create(aluno=self, turma=nova_turma, data_inicio=data)
        self.turma = nova_turma
        self.save(update_fields=["turma"])

    def turma_em(self, data) -> Turma | None:
        """Turma em que o aluno estava na `data`, ou None se ainda não tinha ingressado."""
        periodo = (
            self.historico_turmas.filter(data_inicio__lte=data)
            .filter(Q(data_fim__isnull=True) | Q(data_fim__gt=data))
            .select_related("turma")
            .first()
        )
        return periodo.turma if periodo else None


class HistoricoTurma(HistoricoPreservado):
    """Período em que um aluno esteve numa turma (RN011).

    O período vai de `data_inicio` (inclusive) a `data_fim` (exclusive); o período
    em aberto (`data_fim` vazio) é a turma atual.
    """

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="historico_turmas")
    turma = models.ForeignKey(Turma, on_delete=models.PROTECT, related_name="historico_alunos")
    data_inicio = models.DateField("início")
    data_fim = models.DateField("fim", null=True, blank=True)

    class Meta:
        verbose_name = "histórico de turma"
        verbose_name_plural = "históricos de turma"
        ordering = ["aluno", "data_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["aluno"],
                condition=Q(data_fim__isnull=True),
                name="uma_turma_atual_por_aluno",
            ),
            models.CheckConstraint(
                condition=Q(data_fim__isnull=True) | Q(data_fim__gt=models.F("data_inicio")),
                name="historico_turma_fim_apos_inicio",
            ),
        ]

    def __str__(self):
        fim = self.data_fim or "atual"
        return f"{self.aluno_id} em {self.turma} ({self.data_inicio} a {fim})"


# --- Calendário ----------------------------------------------------------------------


class CicloCalendario(HistoricoPreservado):
    """Ciclo de desempenho: as duas semanas entre simulados (RN006)."""

    data_inicio = models.DateField("início", unique=True)
    data_fim = models.DateField("fim")

    class Meta:
        verbose_name = "ciclo"
        verbose_name_plural = "ciclos"
        ordering = ["data_inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(data_fim__gt=models.F("data_inicio")),
                name="ciclo_fim_apos_inicio",
            ),
        ]

    def __str__(self):
        return f"Ciclo {self.data_inicio:%d/%m/%Y} a {self.data_fim:%d/%m/%Y}"


# --- Registros importados (Ingestão) -------------------------------------------------


class RegistroFrequencia(HistoricoPreservado):
    """Presença de um aluno num dia letivo, apurada a partir da catraca (RN001)."""

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="frequencias")
    data = models.DateField()
    presente = models.BooleanField(help_text="Houve registro na catraca neste dia (RN001).")
    justificada = models.BooleanField(
        default=False, help_text="Ausência justificada e aprovada pela Direção (RN002)."
    )

    class Meta:
        verbose_name = "registro de frequência"
        verbose_name_plural = "registros de frequência"
        ordering = ["aluno", "data"]
        constraints = [
            # Reimportar o mesmo período não duplica registros (NF008).
            models.UniqueConstraint(fields=["aluno", "data"], name="frequencia_unica_por_dia"),
        ]

    def __str__(self):
        return f"{self.aluno_id} em {self.data}: {'presente' if self.presente else 'ausente'}"

    @property
    def eh_falta(self) -> bool:
        """Falta = ausência sem justificativa aprovada (RN001, RN002)."""
        return not self.presente and not self.justificada


class ResultadoSimulado(HistoricoPreservado):
    """Resultado de um aluno numa área do simulado do ciclo (RN010)."""

    class Area(models.TextChoices):
        LINGUAGENS = "LINGUAGENS", "Linguagens e Códigos"
        HUMANAS = "HUMANAS", "Ciências Humanas"
        NATUREZA = "NATUREZA", "Ciências da Natureza"
        MATEMATICA = "MATEMATICA", "Matemática"

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="resultados_simulado")
    ciclo = models.ForeignKey(CicloCalendario, on_delete=models.PROTECT, related_name="simulados")
    area = models.CharField("área", max_length=12, choices=Area.choices)
    presente = models.BooleanField(
        default=True,
        help_text="Ausente no simulado não é avaliado em desempenho no ciclo (RN009).",
    )
    nota_tri = models.DecimalField(
        "nota TRI", max_digits=5, decimal_places=1, null=True, blank=True
    )
    acertos = models.PositiveSmallIntegerField("acertos brutos", null=True, blank=True)

    class Meta:
        verbose_name = "resultado de simulado"
        verbose_name_plural = "resultados de simulado"
        ordering = ["aluno", "ciclo", "area"]
        constraints = [
            models.UniqueConstraint(
                fields=["aluno", "ciclo", "area"], name="simulado_unico_por_ciclo_e_area"
            ),
            models.CheckConstraint(
                condition=Q(presente=True) | Q(nota_tri__isnull=True, acertos__isnull=True),
                name="simulado_ausente_sem_nota",
            ),
        ]

    def __str__(self):
        return f"{self.aluno_id} — {self.get_area_display()} — {self.ciclo}"


COMPETENCIAS_REDACAO = ("nota_c1", "nota_c2", "nota_c3", "nota_c4", "nota_c5")


class ResultadoRedacao(HistoricoPreservado):
    """Entrega e notas por competência de uma redação semanal (RN007)."""

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="redacoes")
    tema_semana = models.DateField(
        "semana do tema", help_text="Terça-feira em que o tema foi lançado (RN007)."
    )
    tema = models.CharField(max_length=200, blank=True)
    entregue = models.BooleanField()
    nota_c1 = models.PositiveSmallIntegerField("competência 1", null=True, blank=True)
    nota_c2 = models.PositiveSmallIntegerField("competência 2", null=True, blank=True)
    nota_c3 = models.PositiveSmallIntegerField("competência 3", null=True, blank=True)
    nota_c4 = models.PositiveSmallIntegerField("competência 4", null=True, blank=True)
    nota_c5 = models.PositiveSmallIntegerField("competência 5", null=True, blank=True)

    COMPETENCIAS = COMPETENCIAS_REDACAO

    class Meta:
        verbose_name = "resultado de redação"
        verbose_name_plural = "resultados de redação"
        ordering = ["aluno", "tema_semana"]
        constraints = [
            models.UniqueConstraint(fields=["aluno", "tema_semana"], name="redacao_unica_por_tema"),
            models.CheckConstraint(
                condition=Q(entregue=True)
                | Q(
                    nota_c1__isnull=True,
                    nota_c2__isnull=True,
                    nota_c3__isnull=True,
                    nota_c4__isnull=True,
                    nota_c5__isnull=True,
                ),
                name="redacao_nao_entregue_sem_nota",
            ),
            *[
                models.CheckConstraint(
                    condition=Q(**{f"{c}__isnull": True}) | Q(**{f"{c}__lte": 200}),
                    name=f"redacao_{c}_ate_200",
                )
                for c in COMPETENCIAS_REDACAO
            ],
        ]

    def __str__(self):
        return f"{self.aluno_id} — tema de {self.tema_semana}"

    @property
    def nota_total(self) -> int | None:
        """Soma das cinco competências (0 a 1000), ou None se alguma faltar."""
        notas = [getattr(self, c) for c in self.COMPETENCIAS]
        return None if None in notas else sum(notas)


# --- Alertas e Intervenções ----------------------------------------------------------


class Alerta(HistoricoPreservado):
    """Sinalização indicativa sobre um aluno (RN012). Sempre traz tipo e motivo (NF004)."""

    class Tipo(models.TextChoices):
        FREQUENCIA = "FREQUENCIA", "Frequência"
        DESEMPENHO = "DESEMPENHO", "Queda de desempenho"
        EVOLUCAO = "EVOLUCAO", "Evolução consistente"

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="alertas")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    motivo = models.TextField(help_text="Por que o aluno foi sinalizado, em linguagem simples.")
    data_geracao = models.DateTimeField("gerado em")
    regra = models.ForeignKey(
        "inteligencia.RegraAlerta",
        on_delete=models.PROTECT,
        related_name="alertas",
        null=True,
        blank=True,
        help_text="Regra e limiar vigentes quando o alerta foi gerado (RF018).",
    )
    ciclo = models.ForeignKey(
        CicloCalendario, on_delete=models.PROTECT, related_name="alertas", null=True, blank=True
    )
    area = models.CharField(
        "área", max_length=12, choices=ResultadoSimulado.Area.choices, blank=True
    )

    class Meta:
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ["-data_geracao"]
        constraints = [
            models.CheckConstraint(condition=~Q(motivo=""), name="alerta_com_motivo"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.aluno_id} ({self.data_geracao:%d/%m/%Y})"


class Intervencao(HistoricoPreservado):
    """Ação da Direção sobre um aluno, com desfecho (RF019).

    Pode estar ligada a um alerta ou não (fluxo secundário do RF019). O desfecho
    pode ser registrado depois.
    """

    class Tipo(models.TextChoices):
        CONTATO = "CONTATO", "Contato"
        CONVERSA = "CONVERSA", "Conversa"
        ENCAMINHAMENTO = "ENCAMINHAMENTO", "Encaminhamento"
        OUTRO = "OUTRO", "Outro"

    class Desfecho(models.TextChoices):
        RESOLVIDO = "RESOLVIDO", "Resolvido"
        EM_ACOMPANHAMENTO = "EM_ACOMPANHAMENTO", "Em acompanhamento"
        SEM_RETORNO = "SEM_RETORNO", "Sem retorno"

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="intervencoes")
    alerta = models.ForeignKey(
        Alerta, on_delete=models.PROTECT, related_name="intervencoes", null=True, blank=True
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="intervencoes_registradas",
        verbose_name="registrada por",
    )
    responsavel = models.CharField(
        "responsável", max_length=150, help_text="Quem conduz a intervenção."
    )
    tipo = models.CharField(max_length=14, choices=Tipo.choices)
    data = models.DateField()
    descricao = models.TextField("descrição")
    desfecho = models.CharField(max_length=17, choices=Desfecho.choices, blank=True)

    class Meta:
        verbose_name = "intervenção"
        verbose_name_plural = "intervenções"
        ordering = ["-data"]

    def __str__(self):
        return f"{self.get_tipo_display()} com {self.aluno_id} em {self.data}"

    def save(self, *args, **kwargs):
        if self.alerta_id and self.alerta.aluno_id != self.aluno_id:
            raise ValueError("A intervenção e o alerta precisam ser do mesmo aluno.")
        super().save(*args, **kwargs)
