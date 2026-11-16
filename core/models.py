"""Modelos da Aplicação Core.

Seguem o Diagrama de Classes e o DER do Relatório Descritivo (Seções 1.4 e 1.5),
com as diferenças registradas na SM #41 e listadas em `docs/modelo-de-dados.md`,
seção "Diferenças em relação ao DER do Lab 03".
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from .historico import HistoricoPreservado, HistoricoQuerySet


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


class AlunoQuerySet(HistoricoQuerySet):
    def ingressados_ate(self, data):
        """Alunos que já ingressaram em `data` (inclusive); base dos indicadores (RN004)."""
        return self.filter(data_ingresso__lte=data)

    def ativos(self):
        return self.filter(situacao=Aluno.Situacao.ATIVO)


class Aluno(HistoricoPreservado):
    """Aluno do CASDvest, identificado unicamente pela matrícula (RN003).

    `turma` é a turma atual. Para trocar de turma use `mudar_turma()`, que
    preserva o histórico (RN011). `situacao` e `data_saida` registram desligamento,
    evasão ou matrícula lançada por engano (`INVALIDO`, preservada por causa da NF007).
    """

    class Situacao(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        DESLIGADO = "DESLIGADO", "Desligado"
        EVADIDO = "EVADIDO", "Evadido"
        INVALIDO = "INVALIDO", "Inválido (lançado por engano)"

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
    situacao = models.CharField(
        "situação", max_length=10, choices=Situacao.choices, default=Situacao.ATIVO
    )
    data_saida = models.DateField("data de saída", null=True, blank=True)

    objects = AlunoQuerySet.as_manager()

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"
        ordering = ["nome"]
        constraints = [
            models.CheckConstraint(condition=~Q(matricula=""), name="aluno_matricula_preenchida"),
            models.CheckConstraint(
                condition=~Q(situacao="ATIVO") | Q(data_saida__isnull=True),
                name="aluno_ativo_sem_data_saida",
            ),
            models.CheckConstraint(
                condition=~Q(situacao__in=["DESLIGADO", "EVADIDO"])
                | Q(data_saida__gte=models.F("data_ingresso")),
                name="aluno_saida_apos_ingresso",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.matricula})"

    def clean(self):
        super().clean()
        if self.situacao == self.Situacao.ATIVO and self.data_saida:
            raise ValidationError({"data_saida": "Aluno ativo não tem data de saída."})
        if self.situacao in (self.Situacao.DESLIGADO, self.Situacao.EVADIDO):
            if not self.data_saida:
                raise ValidationError({"data_saida": "Informe a data de saída."})
            if self.data_ingresso and self.data_saida < self.data_ingresso:
                raise ValidationError({"data_saida": "A saída não pode ser anterior ao ingresso."})

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

    @transaction.atomic
    def corrigir_ingresso(self, data):
        """Corrige a data de ingresso e o início do primeiro período de turma (RN004, RN011)."""
        primeiro = self.historico_turmas.order_by("data_inicio").first()
        if primeiro and primeiro.data_fim and data >= primeiro.data_fim:
            raise ValueError("O ingresso deve ser anterior ao fim do primeiro período de turma.")
        self.data_ingresso = data
        self.save(update_fields=["data_ingresso"])
        if primeiro:
            primeiro.data_inicio = data
            primeiro.save(update_fields=["data_inicio"])

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


class PeriodoLetivo(HistoricoPreservado):
    """Período de aulas (início e fim de período; as férias ficam entre dois períodos). RN005."""

    inicio = models.DateField("início", unique=True)
    fim = models.DateField()
    descricao = models.CharField("descrição", max_length=100, blank=True)

    class Meta:
        verbose_name = "período letivo"
        verbose_name_plural = "períodos letivos"
        ordering = ["inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__gte=models.F("inicio")),
                name="periodo_fim_nao_antes_do_inicio",
                violation_error_message="O fim do período não pode ser anterior ao início.",
            ),
        ]

    def __str__(self):
        return f"Período {self.inicio:%d/%m/%Y} a {self.fim:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.inicio and self.fim:
            outros = PeriodoLetivo.objects.exclude(pk=self.pk).filter(
                inicio__lte=self.fim, fim__gte=self.inicio
            )
            if outros.exists():
                raise ValidationError("O período se sobrepõe a outro período letivo (RN005).")


class DiaCalendario(HistoricoPreservado):
    """Exceção ao período: feriado ou emenda (não letivo), sábado com aula (letivo). RN005."""

    data = models.DateField(unique=True)
    letivo = models.BooleanField("dia letivo")
    descricao = models.CharField("descrição", max_length=100, blank=True)

    class Meta:
        verbose_name = "dia do calendário"
        verbose_name_plural = "dias do calendário"
        ordering = ["data"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} ({'letivo' if self.letivo else 'não letivo'})"


class CicloCalendario(HistoricoPreservado):
    """Ciclo de desempenho: as duas semanas entre simulados (RN006)."""

    data_inicio = models.DateField("início", unique=True)
    data_fim = models.DateField("fim")
    data_simulado = models.DateField("data do simulado", null=True, blank=True)

    class Meta:
        verbose_name = "ciclo"
        verbose_name_plural = "ciclos"
        ordering = ["data_inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(data_fim__gt=models.F("data_inicio")),
                name="ciclo_fim_apos_inicio",
            ),
            models.CheckConstraint(
                condition=Q(data_simulado__isnull=True)
                | Q(
                    data_simulado__gte=models.F("data_inicio"),
                    data_simulado__lte=models.F("data_fim"),
                ),
                name="ciclo_simulado_dentro_do_ciclo",
                violation_error_message="A data do simulado deve estar dentro do ciclo.",
            ),
        ]

    def __str__(self):
        return f"Ciclo {self.data_inicio:%d/%m/%Y} a {self.data_fim:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.data_inicio and self.data_fim:
            outros = CicloCalendario.objects.exclude(pk=self.pk).filter(
                data_inicio__lte=self.data_fim, data_fim__gte=self.data_inicio
            )
            if outros.exists():
                raise ValidationError("O ciclo se sobrepõe a outro ciclo (RN006).")
        if self.pk and self.simulados.exists():
            salvo = CicloCalendario.objects.get(pk=self.pk)
            campos = ("data_inicio", "data_fim", "data_simulado")
            if any(getattr(salvo, c) != getattr(self, c) for c in campos):
                raise ValidationError(
                    "O ciclo já tem resultados de simulado: as datas do ciclo são fixas, "
                    "definidas no início do ano (RN006, RF004)."
                )


class TemaRedacao(HistoricoPreservado):
    """Tema da redação semanal, divulgado às terças-feiras; vale até a segunda seguinte (RN007)."""

    data = models.DateField("terça-feira do tema", unique=True)
    tema = models.CharField(max_length=200)

    class Meta:
        verbose_name = "tema de redação"
        verbose_name_plural = "temas de redação"
        ordering = ["data"]
        constraints = [
            models.CheckConstraint(
                condition=Q(data__week_day=3),
                name="tema_lancado_na_terca",
                violation_error_message="O tema é divulgado às terças-feiras (RN007).",
            ),
        ]

    def __str__(self):
        return f"{self.data:%d/%m/%Y}: {self.tema}"

    def clean(self):
        super().clean()
        if self.data and self.data.weekday() != 1:
            raise ValidationError({"data": "O tema é divulgado às terças-feiras (RN007)."})


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


def _competencia(rotulo):
    # Decimal com uma casa: a banca VUNESP do Corrija-me dá notas como 21,4 (RF005).
    return models.DecimalField(rotulo, max_digits=4, decimal_places=1, null=True, blank=True)


class ResultadoRedacao(HistoricoPreservado):
    """Entrega e notas por competência de uma redação semanal (RN007).

    A escala depende da banca do Corrija-me: ENEM tem cinco competências de 0 a 200; outras
    bancas (VUNESP) têm menos critérios e notas decimais, e a nota final vem da banca."""

    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name="redacoes")
    tema_semana = models.DateField(
        "semana do tema", help_text="Terça-feira em que o tema foi lançado (RN007)."
    )
    tema = models.CharField(max_length=200, blank=True)
    entregue = models.BooleanField()
    banca = models.CharField(max_length=80, blank=True, help_text="Banca do Corrija-me.")
    nota_c1 = _competencia("competência 1")
    nota_c2 = _competencia("competência 2")
    nota_c3 = _competencia("competência 3")
    nota_c4 = _competencia("competência 4")
    nota_c5 = _competencia("competência 5")
    nota_final = models.DecimalField(
        "nota final", max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Nota final informada pela banca.",
    )  # fmt: skip

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
                    nota_final__isnull=True,
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
    def nota_total(self):
        """A nota final da banca ou, sem ela, a soma das cinco competências (ENEM, 0 a 1000);
        None se faltar alguma."""
        if self.nota_final is not None:
            return self.nota_final
        notas = [getattr(self, c) for c in self.COMPETENCIAS]
        return None if None in notas else sum(notas)


# --- Alertas e Intervenções ----------------------------------------------------------


class Alerta(HistoricoPreservado):
    """Sinalização indicativa sobre um aluno (RN012). Sempre traz tipo e motivo (NF004).

    No máximo um alerta de cada tipo por aluno e semana (NF005): o de frequência é da
    `semana` (segunda-feira); o de desempenho, do `ciclo`. Regerar os alertas atualiza o
    mesmo registro; o que deixou de valer (dado corrigido) fica `ativo=False`, nunca é
    excluído (NF007)."""

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
    semana = models.DateField(
        null=True, blank=True, help_text="Segunda-feira da semana do alerta de frequência."
    )
    ativo = models.BooleanField(
        default=True, help_text="Desligado quando o dado que o gerou foi corrigido."
    )

    class Meta:
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ["-data_geracao"]
        constraints = [
            models.CheckConstraint(condition=~Q(motivo=""), name="alerta_com_motivo"),
            models.UniqueConstraint(
                fields=["aluno", "tipo", "semana"],
                condition=Q(semana__isnull=False),
                name="um_alerta_por_tipo_e_semana",
            ),
            models.UniqueConstraint(
                fields=["aluno", "tipo", "ciclo"],
                condition=Q(ciclo__isnull=False),
                name="um_alerta_por_tipo_e_ciclo",
            ),
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


# --- Auditoria (NF009) ---------------------------------------------------------------


class RegistroAlteracao(HistoricoPreservado):
    """Uma alteração de um campo: quem, quando, valor anterior e novo (NF009).

    Genérico e sem `GenericForeignKey`: a chave de `Aluno` é texto, então o objeto é
    identificado por `modelo` (`_meta.label_lower`) e `objeto_id` (texto). Nunca guarda
    senha, hash ou token.
    """

    autor = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="alteracoes_registradas"
    )
    modelo = models.CharField(max_length=100)
    objeto_id = models.CharField(max_length=64)
    campo = models.CharField(max_length=64)
    valor_anterior = models.TextField("valor anterior", blank=True)
    valor_novo = models.TextField("valor novo", blank=True)

    class Meta:
        verbose_name = "registro de alteração"
        verbose_name_plural = "registros de alteração"
        ordering = ["-criado_em", "-id"]
        indexes = [models.Index(fields=["modelo", "objeto_id"])]

    def __str__(self):
        return f"{self.modelo}#{self.objeto_id}.{self.campo} por {self.autor_id}"


class RegistroImportacao(HistoricoPreservado):
    """Trilha de uploads: quem importou qual arquivo e quando (RF006, NF007, NF009).

    Guarda só o nome do arquivo, o tamanho e as contagens do resumo. Nunca guarda o
    conteúdo do arquivo, nomes ou matrículas de alunos.
    """

    class Tipo(models.TextChoices):
        CADASTRO = "CADASTRO", "Cadastro de alunos e turmas"
        PERIODOS = "PERIODOS", "Períodos letivos"
        CALENDARIO = "CALENDARIO", "Dias não letivos e exceções"
        CICLOS = "CICLOS", "Ciclos"
        TEMAS = "TEMAS", "Temas de redação"
        FREQUENCIA = "FREQUENCIA", "Frequência (catraca)"
        SIMULADOS = "SIMULADOS", "Simulados (P+)"
        REDACOES = "REDACOES", "Redações (Corrija-me)"

    autor = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="importacoes_registradas"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.CADASTRO)
    nome_arquivo = models.CharField("arquivo", max_length=255)
    tamanho_bytes = models.PositiveBigIntegerField("tamanho (bytes)")
    ano = models.PositiveSmallIntegerField("ano letivo")
    data_mudanca = models.DateField("data de mudança de turma", null=True, blank=True)
    criados = models.PositiveIntegerField(default=0)
    mudancas_turma = models.PositiveIntegerField(default=0)
    atualizados = models.PositiveIntegerField(default=0)
    sem_alteracao = models.PositiveIntegerField(default=0)
    turmas_criadas = models.PositiveIntegerField(default=0)
    divergencias = models.PositiveIntegerField(default=0)
    inconsistentes = models.PositiveIntegerField(default=0)
    pendencias = models.PositiveIntegerField(
        "pendências", default=0, help_text="Linhas sem aluno, à espera de associação (RN003)."
    )

    class Meta:
        verbose_name = "registro de importação"
        verbose_name_plural = "registros de importação"
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return f"{self.tipo} {self.nome_arquivo} por {self.autor_id}"


class PendenciaImportacao(HistoricoPreservado):
    """Linha importada que não casou com um aluno, à espera de associação manual (RN003, NF006).

    Casos: matrícula em branco, fora do padrão, de outro ano letivo, não encontrada ou de
    aluno inválido. Guarda a matrícula e o nome informados (o nome é só sugestão e
    verificação, RN003) e, em `dados`, o que a linha traria (data, presença, notas), para
    ser aplicado quando o Diretor associar a pendência a um aluno. Só o Diretor vê.
    Reimportar a mesma linha encontra a mesma pendência pela `chave` (NF008).
    """

    class Origem(models.TextChoices):
        FREQUENCIA = "FREQUENCIA", "Frequência (catraca)"
        SIMULADO = "SIMULADO", "Simulado (P+)"
        REDACAO = "REDACAO", "Redação (Corrija-me)"

    class Motivo(models.TextChoices):
        EM_BRANCO = "EM_BRANCO", "Matrícula em branco"
        FORA_DO_PADRAO = "FORA_DO_PADRAO", "Matrícula fora do padrão"
        OUTRO_ANO = "OUTRO_ANO", "Matrícula de outro ano letivo"
        NAO_ENCONTRADA = "NAO_ENCONTRADA", "Matrícula não encontrada"
        ALUNO_INVALIDO = "ALUNO_INVALIDO", "Matrícula de aluno inválido"

    class Situacao(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ASSOCIADA = "ASSOCIADA", "Associada"
        DESCARTADA = "DESCARTADA", "Descartada"

    origem = models.CharField(max_length=12, choices=Origem.choices)
    motivo = models.CharField(max_length=16, choices=Motivo.choices)
    ano = models.PositiveSmallIntegerField("ano letivo")
    data = models.DateField(help_text="Dia da passagem, do simulado ou terça do tema.")
    matricula_informada = models.CharField("matrícula informada", max_length=30, blank=True)
    nome_informado = models.CharField("nome informado", max_length=150, blank=True)
    dados = models.JSONField(default=dict, blank=True)
    chave = models.CharField(max_length=64, unique=True, editable=False)
    situacao = models.CharField(
        "situação", max_length=10, choices=Situacao.choices, default=Situacao.PENDENTE
    )
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.PROTECT,
        related_name="pendencias_associadas",
        null=True,
        blank=True,
    )
    resolvida_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="pendencias_resolvidas",
        null=True,
        blank=True,
    )
    resolvida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "pendência de importação"
        verbose_name_plural = "pendências de importação"
        ordering = ["data", "id"]
        indexes = [models.Index(fields=["situacao", "origem", "ano"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(situacao="ASSOCIADA") | Q(aluno__isnull=False),
                name="pendencia_associada_tem_aluno",
            ),
            models.CheckConstraint(
                condition=Q(situacao="PENDENTE")
                | Q(resolvida_por__isnull=False, resolvida_em__isnull=False),
                name="pendencia_resolvida_tem_autor",
            ),
        ]

    def __str__(self):
        return f"{self.get_origem_display()} em {self.data}: {self.get_situacao_display()}"
