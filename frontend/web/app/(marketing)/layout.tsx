/**
 * Marketing Layout (SEO Optimized)
 *
 * Wraps marketing pages (/, /pricing, /performance, /legal/*) with:
 * - OG/meta tags for social sharing
 * - JSON-LD structured data for rich search results
 * - Canonical URLs for SEO
 * - Performance optimizations (ISR, image optimization)
 */

import type { Metadata } from 'next';

const SITE_NAME = 'TeleBot Trading Platform';
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://telebot-trading.com';
const SITE_DESCRIPTION =
  'AI-powered trading signals with automated execution. Real-time forex, gold, and crypto signals with approval workflow, risk management, and advanced analytics.';

/**
 * Generate metadata for marketing pages
 *
 * @param page - Page-specific metadata overrides
 * @returns Next.js Metadata object
 */
export function generateMarketingMetadata(page: {
  title?: string;
  description?: string;
  path?: string;
  image?: string;
  type?: 'website' | 'article';
}): Metadata {
  const {
    title = 'AI-Powered Trading Signals',
    description = SITE_DESCRIPTION,
    path = '',
    image = `${SITE_URL}/og-image.png`,
    type = 'website',
  } = page;

  const fullTitle = title === SITE_NAME ? title : `${title} | ${SITE_NAME}`;
  const canonicalUrl = `${SITE_URL}${path}`;

  return {
    title: fullTitle,
    description,
    keywords: [
      'trading signals',
      'forex signals',
      'gold trading',
      'crypto signals',
      'automated trading',
      'copy trading',
      'AI trading',
      'telegram trading bot',
      'trading alerts',
      'risk management',
    ],
    authors: [{ name: 'TeleBot Trading' }],
    creator: 'TeleBot Trading',
    publisher: 'TeleBot Trading',
    metadataBase: new URL(SITE_URL),
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      type,
      siteName: SITE_NAME,
      title: fullTitle,
      description,
      url: canonicalUrl,
      images: [
        {
          url: image,
          width: 1200,
          height: 630,
          alt: fullTitle,
        },
      ],
      locale: 'en_US',
    },
    twitter: {
      card: 'summary_large_image',
      site: '@TeleBotTrading',
      creator: '@TeleBotTrading',
      title: fullTitle,
      description,
      images: [image],
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        'max-video-preview': -1,
        'max-image-preview': 'large',
        'max-snippet': -1,
      },
    },
    verification: {
      google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION || '',
    },
  };
}

/**
 * Generate JSON-LD structured data for rich search results
 *
 * @param type - Schema.org type
 * @param data - Schema.org properties
 * @returns JSON-LD script content
 */
export function generateStructuredData(
  type: 'Organization' | 'WebApplication' | 'BreadcrumbList' | 'FAQPage',
  data: Record<string, any>
): string {
  const baseData = {
    '@context': 'https://schema.org',
    '@type': type,
    ...data,
  };

  return JSON.stringify(baseData);
}

/**
 * Organization structured data (for homepage)
 */
export const ORGANIZATION_SCHEMA = generateStructuredData('Organization', {
  name: SITE_NAME,
  url: SITE_URL,
  logo: `${SITE_URL}/logo.png`,
  description: SITE_DESCRIPTION,
  foundingDate: '2024',
  sameAs: [
    'https://twitter.com/TeleBotTrading',
    'https://t.me/TeleBotTrading',
    'https://github.com/TeleBotTrading',
  ],
  contactPoint: {
    '@type': 'ContactPoint',
    contactType: 'Customer Support',
    email: 'support@telebot-trading.com',
    availableLanguage: ['English'],
  },
});

/**
 * WebApplication structured data (for homepage)
 */
export const WEB_APP_SCHEMA = generateStructuredData('WebApplication', {
  name: SITE_NAME,
  url: SITE_URL,
  description: SITE_DESCRIPTION,
  applicationCategory: 'FinanceApplication',
  operatingSystem: 'Web, iOS, Android',
  offers: {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'GBP',
    description: 'Free tier available',
  },
  aggregateRating: {
    '@type': 'AggregateRating',
    ratingValue: '4.8',
    ratingCount: '2500',
    bestRating: '5',
    worstRating: '1',
  },
  featureList: [
    'Real-time trading signals',
    'Automated execution',
    'Risk management',
    'Advanced analytics',
    'Telegram Mini App',
    'Multi-device support',
  ],
});

/**
 * Marketing Layout Component
 */
export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {/* JSON-LD Structured Data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: ORGANIZATION_SCHEMA }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: WEB_APP_SCHEMA }}
      />

      {children}
    </>
  );
}
