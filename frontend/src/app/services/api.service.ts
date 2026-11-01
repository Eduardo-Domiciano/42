import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  ArticleLookupResponse,
  ArticleOut,
  ThemeOption,
  TopicQueryOut,
} from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  listThemes(): Observable<{ themes: ThemeOption[] }> {
    return this.http.get<{ themes: ThemeOption[] }>(`${this.base}/themes`);
  }

  lookupArticle(payload: {
    url?: string | null;
    title?: string | null;
    text?: string | null;
    published_at?: string | null;
  }): Observable<ArticleLookupResponse> {
    return this.http.post<ArticleLookupResponse>(
      `${this.base}/articles/lookup`,
      {
        url: payload.url?.trim() || null,
        title: payload.title?.trim() || null,
        text: payload.text?.trim() || null,
        published_at: payload.published_at || null,
      },
    );
  }

  getArticle(articleId: number, themes: string[] = []): Observable<ArticleOut> {
    const params =
      themes.length > 0 ? { themes: themes.join(',') } : undefined;
    return this.http.get<ArticleOut>(`${this.base}/articles/${articleId}`, {
      params,
    });
  }

  reanalyzeArticle(
    articleId: number,
    themes: string[] = [],
    refresh = true,
  ): Observable<ArticleOut> {
    return this.http.post<ArticleOut>(
      `${this.base}/articles/${articleId}/reanalyze`,
      { themes, refresh },
    );
  }

  ingestUrl(url: string, themes: string[] = []): Observable<ArticleOut> {
    return this.http.post<ArticleOut>(`${this.base}/ingest/url`, {
      url,
      themes,
    });
  }

  ingestText(
    text: string,
    title?: string | null,
    publishedAt?: string | null,
    themes: string[] = [],
  ): Observable<ArticleOut> {
    return this.http.post<ArticleOut>(`${this.base}/ingest/text`, {
      text,
      title: title?.trim() || null,
      published_at: publishedAt || null,
      themes,
    });
  }

  searchTopic(payload: {
    topic: string;
    date_from?: string | null;
    date_to?: string | null;
    on_date?: string | null;
    themes?: string[];
  }): Observable<TopicQueryOut> {
    return this.http.post<TopicQueryOut>(`${this.base}/search/topic`, payload);
  }
}
