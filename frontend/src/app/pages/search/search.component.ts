import { CommonModule } from '@angular/common';
import { Component, HostListener, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ArticleOut, ThemeOption, TopicQueryOut } from '../../models/api.models';
import { ApiService } from '../../services/api.service';

type SearchMode = 'url' | 'topic' | 'text';

export interface GlossaryEntry {
  term: string;
  meaning: string;
}

export interface AnalysisStep {
  title: string;
  detail: string;
}

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './search.component.html',
  styleUrl: './search.component.css',
})
export class SearchComponent implements OnInit {
  private readonly api = inject(ApiService);

  mode: SearchMode = 'url';
  url = '';
  topic = '';
  pastedText = '';
  pastedTitle = '';
  pastedDate = '';
  dateFrom = '';
  dateTo = '';
  /** Temas oficiais disponíveis (API); multi-seleção. */
  availableThemes: ThemeOption[] = [];
  /** Slugs marcados pelo usuário (ex.: economia). */
  selectedThemes: string[] = [];
  themesOpen = false;
  /** Mês YYYY-MM; na busca vira o intervalo do 1º ao último dia. */
  onMonth = '';
  /** 0 = nenhum; 1–12 = mês do dropdown. */
  monthPickerMonth = 0;
  monthPickerYear = new Date().getFullYear();
  readonly monthLabels = [
    'Janeiro',
    'Fevereiro',
    'Março',
    'Abril',
    'Maio',
    'Junho',
    'Julho',
    'Agosto',
    'Setembro',
    'Outubro',
    'Novembro',
    'Dezembro',
  ] as const;
  /** Anos disponíveis no seletor (5 atrás → 2 à frente). */
  readonly monthYearOptions: number[] = (() => {
    const y = new Date().getFullYear();
    return Array.from({ length: 8 }, (_, i) => y - 5 + i);
  })();

  loading = false;
  error: string | null = null;
  articleResult: ArticleOut | null = null;
  topicResult: TopicQueryOut | null = null;
  /** IDs de publicações abertas na lista do tema */
  expandedArticleIds = new Set<number>();

  glossaryOpen = false;
  paramsOpen = false;
  analysisOpen = false;

  /** Passo a passo do pipeline (linguagem simples, espelha o backend). */
  readonly analysisSteps: AnalysisStep[] = [
    {
      title: 'Entrada',
      detail:
        'Você cola uma URL, cola o texto da matéria ou digita um tema (com período opcional). No tema, o sistema busca no acervo local e na web; só entram matérias que passam no filtro de relevância (veja o botão P).',
    },
    {
      title: 'Baixar e ler a matéria',
      detail:
        'A página é baixada e o texto útil é extraído (título, corpo, data, autor). Links citados no artigo também são guardados. Se a mesma URL já estava no acervo e o conteúdo não mudou, a análise em cache pode ser reaproveitada.',
    },
    {
      title: 'Fonte (catálogo)',
      detail:
        'O domínio é cruzado com o catálogo brasileiro: quem é o dono (ownership), o nível de autoridade (tier) e o viés editorial habitual (bias). Isso não diz se a matéria é verdadeira — só contextualiza o veículo.',
    },
    {
      title: 'Tipo de conteúdo',
      detail:
        'Regras classificam se parece artigo, opinião, editorial, documento oficial etc. O tipo aparece em Dados Técnicos.',
    },
    {
      title: 'Claims / F3 (afirmativas)',
      detail:
        'O texto é quebrado em frases checáveis (“X fez Y”). Cada uma recebe veredito e notas (temporal, geográfico, partidário, distorção, suporte) usando só o que está na própria matéria — sem consultar outras fontes ainda.',
    },
    {
      title: 'Análise preliminar + resumo',
      detail:
        'Com fonte, tipo e claims, monta-se o veredito preliminar e o resumo em português simples (templates; sem depender de LLM). Tudo fica gravado no snapshot para a próxima vez.',
    },
    {
      title: 'Temas oficiais (opcional)',
      detail:
        'No formulário você marca um ou mais temas (hoje: Economia). Com Economia, a comparação numérica usa séries do Banco Central e o cruzamento prioriza fontes oficiais desse tema. Sem tema marcado, essas análises extras não rodam.',
    },
    {
      title: 'Cross-reference / F4 (cruzamento)',
      detail:
        'As afirmativas são comparadas com outras matérias (acervo do mesmo claim primeiro, depois lote/web). Se você marcou temas oficiais, a busca web prioriza órgãos desses temas (ex.: BCB, IBGE, Fazenda). O sistema vê quem apoia ou refuta, ownership, veto de fonte oficial e a calibração entre o veredito isolado (F3) e o consenso (F4).',
    },
    {
      title: 'Exibição na tela',
      detail:
        'Ordem típica: preview do texto → links citados → resumo da análise → (se Economia) comparação BCB → Dados Técnicos. Badge “Do acervo” indica análise reutilizada do cache.',
    },
  ];

  ngOnInit(): void {
    this.api.listThemes().subscribe({
      next: (res) => {
        this.availableThemes = res.themes ?? [];
      },
      error: () => {
        this.availableThemes = [
          {
            slug: 'economia',
            label: 'Economia',
            description:
              'Confronta números do texto com séries oficiais do Banco Central (Selic, IPCA, dólar).',
          },
        ];
      },
    });
  }

  isThemeSelected(slug: string): boolean {
    return this.selectedThemes.includes(slug);
  }

  toggleTheme(slug: string, checked: boolean): void {
    if (checked) {
      if (!this.selectedThemes.includes(slug)) {
        this.selectedThemes = [...this.selectedThemes, slug];
      }
      return;
    }
    this.selectedThemes = this.selectedThemes.filter((s) => s !== slug);
  }

  themesSummary(): string {
    if (!this.selectedThemes.length) {
      return 'Nenhum (opcional)';
    }
    const labels = this.availableThemes
      .filter((t) => this.selectedThemes.includes(t.slug))
      .map((t) => t.label);
    return labels.length ? labels.join(', ') : this.selectedThemes.join(', ');
  }

  toggleThemesPanel(): void {
    this.themesOpen = !this.themesOpen;
  }

  closeThemesPanel(): void {
    this.themesOpen = false;
  }

  /** Critérios de aceite na busca por tema (espelha o backend). */
  readonly paramsRelevant: string[] = [
    'Camada 1 (claro sim): tokens do tema no texto + score lexical ≥ 0,30 (título vale mais que corpo).',
    'Também aceita: frase do tema no texto; muitos tokens no título; ou embeddings (semântico ≥ 0,48) com algum overlap.',
    'Camada 2 (zona cinza): soft lexical — algum overlap real e score ≥ 0,20.',
    'Período De/Até ou um mês: publicação do artigo dentro do intervalo (máx. 1 mês entre De e Até; “um mês” = mês civil inteiro).',
  ];

  /** Critérios de descarte na busca por tema. */
  readonly paramsDiscarded: string[] = [
    'Zero tokens do tema e score muito baixo → lixo óbvio, descartado sem LLM.',
    'Soft lexical não alcançado (poucos tokens / score baixo).',
    'Com período: sem data de publicação ou data fora do intervalo.',
    'Busca web bloqueada (DuckDuckGo rate-limit) → sem URLs novas; só acervo local entra no filtro.',
    'Falha ao baixar a página (fetch) → URL não vira artigo.',
  ];

  /** Termos da UI com significado curto (EN + PT). */
  readonly glossaryEntries: GlossaryEntry[] = [
    {
      term: 'Bias (viés / parcialidade)',
      meaning:
        'Tendência editorial da fonte (esquerda, centro, direita, institucional). Não julga se a matéria é falsa; só indica orientação habitual.',
    },
    {
      term: 'Ownership (grupo dono)',
      meaning:
        'Quem controla o veículo (grupo de mídia, governo, partido). Ajuda a ver se várias “fontes” na verdade são o mesmo dono.',
    },
    {
      term: 'Claims / F3 (afirmativas)',
      meaning:
        'Frases checáveis tiradas do texto (“X fez Y”). O F3 avalia cada afirmativa só com o que está na própria matéria.',
    },
    {
      term: 'Tabela Claims (colunas)',
      meaning:
        'Cada linha é uma afirmativa. Claim = texto canônico. Veredito = conclusão isolada. Confiança = certeza do veredito (0%–100%). Temporal / Geográfico / Partidário / Distorção / Suporte = notas 0,00–1,00. Método = como foi calculado (heurística, LLM, NLI…).',
    },
    {
      term: 'Escala das notas (mín. e máx.)',
      meaning:
        'Notas numéricas vão de 0,00 (mínimo) a 1,00 (máximo). Confiança aparece em porcentagem: 0% a 100% (equivale a 0,00–1,00). Valores no meio são parciais — não são “nota escolar”, e sim intensidade do sinal.',
    },
    {
      term: 'Temporal (âncora de tempo)',
      meaning:
        '0,00 = sem data/período útil. 1,00 = afirmativa bem ancorada no tempo (data no texto e/ou data de publicação do artigo). Quanto maior, mais clara a “quando”.',
    },
    {
      term: 'Geográfico (âncora de lugar)',
      meaning:
        '0,00 = quase sem lugar/instituição. 1,00 = forte âncora de local ou entidade (ex.: Brasil, STF, Brasília). Ajuda a situar o “onde / quem institucional”.',
    },
    {
      term: 'Partidário (sinal político)',
      meaning:
        '0,00 = pouco framing político explícito. 1,00 = muitos marcadores partidários/polêmica. Aqui, alto = mais risco de enquadramento político — não é “nota boa”.',
    },
    {
      term: 'Distorção (clickbait / sensacionalismo)',
      meaning:
        '0,00 = título e corpo alinhados, tom sóbrio. 1,00 = sensacionalismo ou título pouco coerente com o corpo. Alto = alerta de distorção.',
    },
    {
      term: 'Suporte (evidência interna)',
      meaning:
        '0,00 = quase sem evidência dentro do próprio artigo. 1,00 = números, citações, links ou trechos que sustentam a afirmativa no texto. Alto = mais lastro interno (ainda sem cruzar fontes externas).',
    },
    {
      term: 'Confiança (do veredito)',
      meaning:
        '0% = veredito muito incerto. 100% = método está bem seguro daquele veredito isolado. Não prova verdade absoluta; só mede certeza da avaliação das afirmativas.',
    },
    {
      term: 'Cross-reference / F4 (cruzamento)',
      meaning:
        'Compara as afirmativas com outras matérias e fontes. O F4 monta o panorama: quem apoia, quem refuta e o nível de consenso.',
    },
    {
      term: 'Consensus (consenso entre fontes)',
      meaning:
        'Quanto as fontes independentes convergem sobre a mesma afirmativa. Poucas fontes ou o mesmo dono = consenso frágil.',
    },
    {
      term: 'Calibration (calibração F3 vs F4)',
      meaning:
        'Diferença entre o veredito isolado (só o artigo) e o consenso externo. Se divergem, a análise destaca o alerta.',
    },
    {
      term: 'Stance (posição da evidência)',
      meaning:
        'Se outra matéria apoia (supports), refuta (refutes), só se relaciona (related) ou não fala do mesmo ponto (unrelated).',
    },
    {
      term: 'Primary veto (veto de fonte oficial)',
      meaning:
        'Quando existe documento ou fonte primária/oficial no conjunto, o veredito fica mais cauteloso se ela contradisser o resto.',
    },
    {
      term: 'Fonte oficial (primary) por tema',
      meaning:
        'Órgãos e portais do Estado (tier primary). Se você marcar Economia, o cruzamento prioriza BCB, IBGE, Ipea, Fazenda, Tesouro, CVM etc. Sem tema marcado, a busca web não força esses sites oficiais.',
    },
    {
      term: 'Temas oficiais',
      meaning:
        'Seleção opcional no formulário (multi). Hoje: Economia. Define se entram análises extras com fontes oficiais daquele tema.',
    },
    {
      term: 'Comparação BCB (economia)',
      meaning:
        'Só roda se você marcar o tema Economia. Busca séries anuais na API SGS do Banco Central (Selic, IPCA, dólar), grava no banco e compara números das afirmativas com o valor oficial do ano.',
    },
    {
      term: 'Score (pontuação) e Tier (nível)',
      meaning:
        'Score resume confiança/qualidade heurística. Tier classifica a autoridade da fonte (primária, secundária, baixa…).',
    },
    {
      term: 'Framing (enquadramento)',
      meaning:
        'Como a história é contada: o que é enfatizado, omitido ou dramatizado, independentemente dos fatos citados.',
    },
    {
      term: 'Acervo (cache)',
      meaning:
        'Análise já gravada no banco e reutilizada. Evita baixar e recalcular o mesmo artigo se o conteúdo não mudou.',
    },
    {
      term: 'Vereditos (Supported / Disputed / Insufficient)',
      meaning:
        'Supported: há suporte interno. Disputed: há tensão ou contestação. Insufficient: falta evidência checável no texto.',
    },
  ];

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.themesOpen) {
      this.closeThemesPanel();
    } else if (this.analysisOpen) {
      this.closeAnalysis();
    } else if (this.glossaryOpen) {
      this.closeGlossary();
    } else if (this.paramsOpen) {
      this.closeParams();
    }
  }

  private lockBodyScroll(): void {
    document.body.style.overflow = 'hidden';
  }

  private unlockBodyScroll(): void {
    document.body.style.overflow = '';
  }

  private anyModalOpen(): boolean {
    return this.glossaryOpen || this.paramsOpen || this.analysisOpen;
  }

  openGlossary(): void {
    this.paramsOpen = false;
    this.analysisOpen = false;
    this.glossaryOpen = true;
    this.lockBodyScroll();
  }

  closeGlossary(): void {
    this.glossaryOpen = false;
    if (!this.anyModalOpen()) {
      this.unlockBodyScroll();
    }
  }

  openParams(): void {
    this.glossaryOpen = false;
    this.analysisOpen = false;
    this.paramsOpen = true;
    this.lockBodyScroll();
  }

  closeParams(): void {
    this.paramsOpen = false;
    if (!this.anyModalOpen()) {
      this.unlockBodyScroll();
    }
  }

  openAnalysis(): void {
    this.glossaryOpen = false;
    this.paramsOpen = false;
    this.analysisOpen = true;
    this.lockBodyScroll();
  }

  closeAnalysis(): void {
    this.analysisOpen = false;
    if (!this.anyModalOpen()) {
      this.unlockBodyScroll();
    }
  }

  setMode(mode: SearchMode): void {
    this.mode = mode;
    this.error = null;
  }
  isArticleExpanded(id: number): boolean {
    return this.expandedArticleIds.has(id);
  }

  toggleArticle(id: number, event?: Event): void {
    event?.preventDefault();
    const next = new Set(this.expandedArticleIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this.expandedArticleIds = next;
  }

  /** Rótulo só em português (UI das tabelas e badges). */
  withPt(_en: string, pt: string): string {
    return pt;
  }

  biasWord(): string {
    return this.withPt('Bias', 'Viés / parcialidade');
  }

  claimsWord(): string {
    return this.withPt('Claims', 'Afirmativas');
  }

  ownershipWord(): string {
    return this.withPt('Ownership', 'Grupo dono');
  }

  scoreWord(): string {
    return this.withPt('Score', 'Pontuação');
  }

  tierWord(): string {
    return this.withPt('Tier', 'Nível de autoridade');
  }

  framingWord(): string {
    return this.withPt('Framing', 'Enquadramento');
  }

  biasLabel(label: string | null | undefined): string {
    const map: Record<string, string> = {
      institutional: 'Institucional',
      left: 'Esquerda',
      center_left: 'Centro-esquerda',
      center: 'Centro',
      center_right: 'Centro-direita',
      right: 'Direita',
      unknown: 'Desconhecida',
    };
    return map[label || 'unknown'] || label || 'Desconhecida';
  }

  contentTypeLabel(type: string | null | undefined): string {
    const map: Record<string, string> = {
      official_document: 'Documento oficial',
      press_release: 'Comunicado',
      opinion: 'Opinião',
      editorial: 'Editorial',
      analysis: 'Análise',
      post: 'Publicação em rede',
      note: 'Nota',
      article: 'Artigo',
    };
    return map[type || 'article'] || type || 'Artigo';
  }

  verdictLabel(verdict: string | null | undefined): string {
    const map: Record<string, string> = {
      supported: 'Com suporte interno',
      disputed: 'Contestável',
      insufficient: 'Evidência insuficiente',
      opinion: 'Opinião',
    };
    return map[verdict || ''] || verdict || '—';
  }

  methodLabel(method: string | null | undefined): string {
    const map: Record<string, string> = {
      heuristic: 'Heurística / regras',
      llm: 'Modelo de IA',
      'llm+source': 'IA + perfil da fonte',
      'heuristic+claims': 'Regras + afirmativas',
      'heuristic+nli': 'Regras + rede neural',
      nli: 'Rede neural (entailment)',
      acervo: 'Acervo (reutilizada do banco)',
    };
    return map[method || ''] || method || '—';
  }

  authorityTierLabel(tier: string | null | undefined): string {
    const map: Record<string, string> = {
      primary: 'Primária / oficial',
      secondary: 'Secundária',
      low: 'Baixa',
      reputable: 'Reputável',
    };
    if (!tier) {
      return '?';
    }
    return map[tier] || `${tier}`;
  }

  stanceLabel(stance: string | null | undefined): string {
    const map: Record<string, string> = {
      supports: 'Apoia',
      refutes: 'Refuta',
      related: 'Relacionada',
      unrelated: 'Não relacionada',
    };
    return map[stance || ''] || stance || '—';
  }

  bcbStatusLabel(status: string | null | undefined): string {
    const map: Record<string, string> = {
      match: 'Coincide com o BCB',
      close: 'Próximo do BCB',
      mismatch: 'Diverge do BCB',
      no_official_data: 'Sem dado oficial no ano',
      year_cached: 'Séries do ano em cache',
      official_series: 'Dado oficial (referência)',
    };
    return map[status || ''] || status || '—';
  }

  crossRefWord(): string {
    return this.withPt('Cross-reference', 'Cruzamento');
  }

  calibrationWord(): string {
    return this.withPt('Calibration', 'Calibração F3 vs F4');
  }

  consensusWord(): string {
    return this.withPt('Consensus', 'Consenso entre fontes');
  }

  vetoWord(): string {
    return this.withPt('Primary veto', 'Veto de fonte oficial');
  }

  summaryParagraphs(text: string | null | undefined): string[] {
    return (text || '')
      .split(/\n\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
  }

  /** Blocos do resumo geral do tema (seções ## + bullets). */
  topicSummarySections(
    text: string | null | undefined,
  ): { title: string; items: { text: string; level: number }[] }[] {
    const sections: { title: string; items: { text: string; level: number }[] }[] =
      [];
    let current: { title: string; items: { text: string; level: number }[] } | null =
      null;

    for (const raw of (text || '').split('\n')) {
      const line = raw.trimEnd();
      const heading = line.match(/^##\s+(.+)$/);
      if (heading) {
        current = { title: heading[1].trim(), items: [] };
        sections.push(current);
        continue;
      }
      if (!current) {
        continue;
      }
      const nested = line.match(/^\s{2}-\s+(.+)$/);
      if (nested) {
        current.items.push({ text: nested[1].trim(), level: 2 });
        continue;
      }
      const bullet = line.match(/^-\s+(.+)$/);
      if (bullet) {
        current.items.push({ text: bullet[1].trim(), level: 1 });
      }
    }
    return sections;
  }

  /** True se Até passa de 1 mês depois de De. */
  private exceedsOneMonth(from: string, to: string): boolean {
    const start = new Date(`${from}T00:00:00`);
    const end = new Date(`${to}T00:00:00`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return false;
    }
    const limit = new Date(start);
    limit.setMonth(limit.getMonth() + 1);
    return end > limit;
  }

  setMonthPickerYear(year: number | string): void {
    const y = Number(year);
    if (!Number.isFinite(y)) {
      return;
    }
    this.monthPickerYear = y;
    this.syncOnMonthFromPickers();
  }

  setMonthPickerMonth(month: number | string): void {
    const m = Number(month);
    if (!Number.isFinite(m) || m < 0 || m > 12) {
      return;
    }
    this.monthPickerMonth = m;
    this.syncOnMonthFromPickers();
  }

  private syncOnMonthFromPickers(): void {
    if (this.monthPickerMonth < 1 || this.monthPickerMonth > 12) {
      this.onMonth = '';
      return;
    }
    this.onMonth = `${this.monthPickerYear}-${String(this.monthPickerMonth).padStart(2, '0')}`;
  }

  clearOnMonth(): void {
    this.onMonth = '';
    this.monthPickerMonth = 0;
  }

  onMonthLabel(): string | null {
    if (!/^\d{4}-\d{2}$/.test(this.onMonth)) {
      return null;
    }
    const month = Number(this.onMonth.slice(5, 7));
    if (month < 1 || month > 12) {
      return null;
    }
    return `${this.monthLabels[month - 1]} de ${this.onMonth.slice(0, 4)}`;
  }

  /** Converte YYYY-MM no 1º e último dia do mês (ISO). */
  private monthRange(ym: string): { from: string; to: string } | null {
    if (!/^\d{4}-\d{2}$/.test(ym)) {
      return null;
    }
    const [y, m] = ym.split('-').map((n) => Number(n));
    if (m < 1 || m > 12) {
      return null;
    }
    const lastDay = new Date(y, m, 0).getDate();
    const to = `${ym}-${String(lastDay).padStart(2, '0')}`;
    return { from: `${ym}-01`, to };
  }

  submit(): void {
    this.error = null;
    this.articleResult = null;
    this.topicResult = null;
    this.expandedArticleIds = new Set();
    this.loading = true;

    if (this.mode === 'url') {
      if (!this.url.trim()) {
        this.loading = false;
        this.error = 'Informe uma URL de notícia.';
        return;
      }
      this.api.ingestUrl(this.url.trim(), this.selectedThemes).subscribe({
        next: (result) => {
          this.articleResult = result;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail || 'Falha ao analisar a URL.';
          this.loading = false;
        },
      });
      return;
    }

    if (this.mode === 'text') {
      const body = this.pastedText.trim();
      if (body.length < 80) {
        this.loading = false;
        this.error = 'Cole um texto com pelo menos cerca de 80 caracteres.';
        return;
      }
      this.api
        .ingestText(
          body,
          this.pastedTitle,
          this.pastedDate || null,
          this.selectedThemes,
        )
        .subscribe({
          next: (result) => {
            this.articleResult = result;
            this.loading = false;
          },
          error: (err) => {
            this.error = err?.error?.detail || 'Falha ao analisar o texto.';
            this.loading = false;
          },
        });
      return;
    }

    if (!this.topic.trim()) {
      this.loading = false;
      this.error = 'Informe um tema para buscar.';
      return;
    }

    let dateFrom = this.dateFrom || null;
    let dateTo = this.dateTo || null;

    if (this.onMonth) {
      const range = this.monthRange(this.onMonth);
      if (!range) {
        this.loading = false;
        this.error = 'Informe um mês válido (AAAA-MM).';
        return;
      }
      dateFrom = range.from;
      dateTo = range.to;
    } else if (dateFrom && dateTo) {
      if (dateFrom > dateTo) {
        this.loading = false;
        this.error = 'A data De não pode ser depois de Até.';
        return;
      }
      if (this.exceedsOneMonth(dateFrom, dateTo)) {
        this.loading = false;
        this.error = 'O intervalo entre De e Até não pode passar de 1 mês.';
        return;
      }
    }

    this.api
      .searchTopic({
        topic: this.topic.trim(),
        date_from: dateFrom,
        date_to: dateTo,
        on_date: null,
        themes: this.selectedThemes,
      })
      .subscribe({
        next: (result) => {
          this.topicResult = result;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail || 'Falha na busca por tema.';
          this.loading = false;
        },
      });
  }
}
