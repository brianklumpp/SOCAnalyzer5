describe('SOCAnalyzer happy path smoke', () => {
  it('navigates from Analyzer to Report and renders summary using stubbed APIs', () => {
    // Stub history to display the View Report button
    cy.intercept('GET', '/history', {
      statusCode: 200,
      body: [
        { id: 'scan-1', filename: 'example.pdf', timestamp: new Date().toISOString(), results: {} }
      ],
    }).as('getHistory');

    // Stub report detail
    cy.intercept('GET', '/report/scan-1', {
      statusCode: 200,
      body: {
        id: 'scan-1',
        company: 'Acme Corp',
        product: 'Widget',
        auditor: 'TrustAudits LLC',
        coverage_period: '2024-01-01 to 2024-12-31',
        coverage_start: '2024-01-01',
        coverage_end: '2024-12-31',
        report_date: '2025-01-15',
        subservice_orgs: [],
        cuecs: [],
        controls: [],
        extracted_text: '...'
      }
    }).as('getReport');

    // Stub framework criteria
    cy.intercept('GET', '/framework_criteria', {
      statusCode: 200,
      body: {
        tsc: { CC: [{ id: 'CC1.1' }] },
        coso: { PR: [{ id: 'PR1' }] }
      }
    }).as('getFramework');

    // Stub executive summary (new JSON structure)
    cy.intercept('GET', '/executive_summary/scan-1', {
      statusCode: 200,
      body: {
        executive_summary: {
          about_company: 'Acme Corp provides widgets.',
          key_findings: ['Strong access controls'],
          areas_of_concern: [],
          recommendations_risk_mitigations: ['Enable MFA everywhere'],
          recommendations_contract_enhancements: ['Add audit rights clause']
        },
      }
    }).as('getExecSummary');

    cy.visit('/');
    cy.wait('@getHistory');
  cy.contains('View Report').click();

  cy.url().should('include', '/app/report/scan-1');
    cy.wait(['@getReport', '@getFramework', '@getExecSummary']);

    // Expect key content on the Report page
    cy.contains('SOC 2 Summary');
    cy.contains('Overview');
    cy.contains('About the Company');
    cy.contains('Recommendations — Risk Mitigations');
  });
});
