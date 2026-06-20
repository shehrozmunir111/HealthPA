import type {
  AskResult,
  ExtractResult,
  PaCase,
  ProposedCode,
  ReviewResult,
} from "./types";

export const MOCK_CASES: PaCase[] = [
  {
    id: "PA-1042",
    request_number: "PA-1042",
    patient: "A. Rahman",
    payer: "Aetna",
    status: "pending",
    created_at: "2026-06-16T09:12:00Z",
    clinical_notes:
      "Adult patient with productive cough, fever, and right basal crackles on exam. " +
      "Assessment: pneumonia, unspecified organism. A two-view chest x-ray was performed " +
      "to evaluate for consolidation.",
  },
  {
    id: "PA-1043",
    request_number: "PA-1043",
    patient: "M. Chen",
    payer: "Cigna",
    status: "needs_info",
    created_at: "2026-06-16T08:40:00Z",
    clinical_notes:
      "Chronic right knee pain and stiffness; imaging consistent with osteoarthritis. " +
      "MRI of the right knee without contrast requested after 6 weeks of failed conservative therapy.",
  },
  {
    id: "PA-1044",
    request_number: "PA-1044",
    patient: "L. Okafor",
    payer: "UnitedHealthcare",
    status: "approved",
    created_at: "2026-06-15T16:05:00Z",
    clinical_notes:
      "Type 2 diabetes mellitus without complications, routine follow-up. " +
      "Hemoglobin A1c laboratory test ordered for glycemic monitoring.",
  },
  {
    id: "PA-1045",
    request_number: "PA-1045",
    patient: "S. Patel",
    payer: "Aetna",
    status: "draft",
    created_at: "2026-06-15T11:20:00Z",
    clinical_notes:
      "Acute bronchitis, unspecified. Symptomatic management; no imaging ordered at this time.",
  },
];

const PROPOSED: Record<string, ProposedCode[]> = {
  "PA-1042": [
    {
      code: "J18.9",
      description: "Pneumonia, unspecified organism",
      code_system: "ICD10",
      confidence: 0.95,
      grounded: true,
      citations: [
        {
          source_doc: "aetna_respiratory.txt",
          chunk: 0,
          quote:
            "Pneumonia, unspecified organism is coded J18.9 under ICD-10-CM.",
        },
      ],
    },
    {
      code: "71046",
      description: "Radiologic exam, chest; 2 views",
      code_system: "CPT",
      confidence: 0.93,
      grounded: true,
      citations: [
        {
          source_doc: "aetna_respiratory.txt",
          chunk: 0,
          quote:
            "A two-view (frontal and lateral) chest x-ray is CPT 71046.",
        },
      ],
    },
  ],
  "PA-1043": [
    {
      code: "M17.11",
      description: "Unilateral primary osteoarthritis, right knee",
      code_system: "ICD10",
      confidence: 0.9,
      grounded: true,
      citations: [
        {
          source_doc: "cigna_msk.txt",
          chunk: 0,
          quote: "Primary osteoarthritis of the right knee is ICD-10-CM M17.11.",
        },
      ],
    },
    {
      code: "73721",
      description: "MRI, lower extremity joint, without contrast",
      code_system: "CPT",
      confidence: 0.88,
      grounded: true,
      citations: [
        {
          source_doc: "cigna_msk.txt",
          chunk: 0,
          quote: "MRI of the knee without contrast is CPT 73721.",
        },
      ],
    },
  ],
  "PA-1044": [
    {
      code: "E11.9",
      description: "Type 2 diabetes mellitus without complications",
      code_system: "ICD10",
      confidence: 0.94,
      grounded: true,
      citations: [
        {
          source_doc: "uhc_diabetes.txt",
          chunk: 0,
          quote:
            "Type 2 diabetes mellitus without complications is ICD-10-CM E11.9.",
        },
      ],
    },
    {
      code: "83036",
      description: "Hemoglobin A1c",
      code_system: "CPT",
      confidence: 0.91,
      grounded: true,
      citations: [
        {
          source_doc: "uhc_diabetes.txt",
          chunk: 0,
          quote: "Hemoglobin A1c (glycated hemoglobin) testing is CPT 83036.",
        },
      ],
    },
  ],
};

export function mockExtract(id: string): ExtractResult {
  const codes = PROPOSED[id] ?? [];
  return {
    status: "pending_review",
    proposed: {
      codes,
      rationale:
        "Codes assigned strictly from retrieved payer policy; one ungrounded suggestion was dropped.",
      grounded: codes.length > 0,
      fallback_used: codes.length === 0,
      notes: codes.length ? "" : "no policy-grounded codes found",
    },
    summary: `Review ${codes.length} proposed code(s)`,
  };
}

export function mockReview(
  id: string,
  decision: string,
  edited?: ProposedCode[]
): ReviewResult {
  const proposed = PROPOSED[id] ?? [];
  let final: ProposedCode[] = [];
  if (decision === "approve") final = proposed;
  else if (decision === "edit") final = edited ?? [];
  return { status: `reviewed:${decision}`, final_codes: final, decision };
}

export function mockAsk(_message: string): AskResult {
  return {
    answer:
      "Per this hospital's Aetna policy, a two-view chest x-ray is CPT 71046 " +
      "(single-view is 71045). Pneumonia, unspecified organism is J18.9. " +
      "Imaging must be supported by documented signs or symptoms.",
    status: "completed",
    grounded: true,
    sources: [
      {
        tool: "search_policies",
        detail:
          "A single-view chest x-ray is CPT 71045. A two-view chest x-ray is CPT 71046.",
        source_doc: "aetna_respiratory.txt",
        chunk: 0,
      },
    ],
  };
}
