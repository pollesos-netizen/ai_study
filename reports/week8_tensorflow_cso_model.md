# 8주차 TensorFlow/Keras C/S/O 등급 예측 모델

## 1. 목적

8주차의 목적은 기존 scikit-learn 기반 문장분류 실습을 TensorFlow/Keras 방식으로 재구현하고, 두 방식의 차이를 이해하는 것이다.

이번 주차에서는 7주차에서 정리한 다중 속성 라벨 전체를 한 번에 예측하지 않고, 우선 `cso_grade`만 예측 대상으로 삼았다.

```text
입력: 문장 text
출력: C / S / O 등급
```

8주차에서 구현한 스크립트는 다음과 같다.

```text
notebooks/05_train_tensorflow_cso_model.py
notebooks/06_test_tensorflow_cso_model.py
notebooks/07_compare_sklearn_tensorflow.py
```

각 스크립트의 역할은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `05_train_tensorflow_cso_model.py` | TensorFlow/Keras char 기반 C/S/O 모델 학습, 평가, 오분류 저장 |
| `06_test_tensorflow_cso_model.py` | 저장된 Keras 모델을 불러와 새 문장 예측 |
| `07_compare_sklearn_tensorflow.py` | scikit-learn 모델과 Keras 모델의 동일 검증 데이터 기준 성능 비교 |

---

## 2. 사용 데이터

사용 데이터는 7주차에서 정리한 최신 CSV이다.

```text
data/privacy_sentence_sample_v4.csv
```

사용 컬럼은 다음과 같다.

```text
text
cso_grade
```

전체 데이터 분포는 다음과 같다.

| 등급 | 건수 |
|---|---:|
| C | 33 |
| S | 78 |
| O | 78 |
| 합계 | 189 |

학습/검증 분리는 `RANDOM_SEED=42`, `VALIDATION_RATIO=0.2` 기준으로 수행했다.

| 구분 | 건수 |
|---|---:|
| 학습 데이터 | 152 |
| 검증 데이터 | 37 |

검증 데이터 분포는 다음과 같다.

| 등급 | 건수 |
|---|---:|
| C | 8 |
| S | 16 |
| O | 13 |

---

## 3. TensorFlow/Keras 모델 구조

8주차 TensorFlow/Keras 모델은 한국어 형태소 분석기를 사용하지 않고, char 단위 `TextVectorization`을 사용했다.

모델 구조는 다음과 같다.

```text
TextVectorization(split="character")
→ Embedding
→ GlobalAveragePooling1D
→ Dense(64, relu)
→ Dropout(0.3)
→ Dense(3, softmax)
```

코드상 핵심 구조는 다음과 같다.

```python
vectorizer = layers.TextVectorization(
    max_tokens=MAX_TOKENS,
    output_mode="int",
    output_sequence_length=SEQUENCE_LENGTH,
    split="character",
    name="char_vectorizer",
)

model = keras.Sequential([
    vectorizer,
    layers.Embedding(input_dim=MAX_TOKENS, output_dim=EMBEDDING_DIM),
    layers.GlobalAveragePooling1D(),
    layers.Dense(DENSE_UNITS, activation="relu"),
    layers.Dropout(DROPOUT_RATE),
    layers.Dense(3, activation="softmax"),
])
```

출력층은 `Dense(3, activation="softmax")`를 사용했다.

이는 C/S/O 세 등급 중 하나를 선택하는 단일 라벨 분류 문제이기 때문이다.

---

## 4. char 단위 전처리를 사용한 이유

한국어 문장은 띄어쓰기, 조사, 어미 변화의 영향을 많이 받는다.

예를 들어 다음 표현들은 의미상 유사하지만 word 단위로는 서로 다른 토큰이 될 수 있다.

```text
이메일은
이메일이
이메일입니다
이메일 주소는
```

char 단위 전처리는 이런 표현 차이에 비교적 강하다.

또한 개인정보/민감정보 탐지에는 다음과 같은 패턴도 중요하다.

```text
test@example.com
010-1234-5678
192.168.0.1
VLAN 100
계약 단가
입찰 평가
건강검진
```

따라서 8주차 기본 실습에서는 별도의 한국어 형태소 분석기 없이 char 단위 TextVectorization을 우선 적용했다.

---

## 5. TensorFlow/Keras 학습 결과

`05_train_tensorflow_cso_model.py` 실행 결과는 다음과 같다.

```text
검증 손실: 1.0561
검증 정확도: 0.5946
```

마지막 epoch 지표는 다음과 같다.

```text
accuracy: 0.5066
loss: 0.9977
val_accuracy: 0.5946
val_loss: 1.0561
```

검증 정확도는 약 59.46%로 확인되었다.

다만 샘플 예측 확률을 보면 모델의 확신도는 전반적으로 낮았다.

예시:

```text
회의 결과를 요약하여 공유드립니다.
예측 등급: O
확률: C=0.169, S=0.412, O=0.419
```

예측 등급은 O였지만 S와 O의 확률 차이가 매우 작다.

이 결과는 모델이 아직 C/S/O 기준을 강하게 학습하지 못했다는 점을 보여준다.

---

## 6. Keras 모델 오분류 분석

검증 데이터 37개 중 오분류는 15개였다.

```text
정분류: 22개
오분류: 15개
정확도: 22 / 37 = 0.5946
```

오분류 예시는 다음과 같다.

| 문장 | 실제 등급 | 예측 등급 |
|---|---|---|
| 해당 구간 시설물의 취약 부위를 식별했습니다 | C | O |
| 장애인 복지카드 사본을 제출했습니다. | C | S |
| 부서별 원가율 현황을 보고드립니다 | C | O |
| 법적 리스크 검토 의견서를 첨부합니다 | C | O |
| 장비 취약점 점검 결과를 보고드립니다 | C | O |
| 해당 직원의 휴가 신청을 승인했습니다 | O | S |
| 행사 참가 신청서가 접수되었습니다 | O | S |
| 부서 간 협조 요청 서류가 접수되었습니다 | O | S |

오분류 분석 결과, Keras 모델은 특히 C 등급을 약하게 예측했다.

C 등급 문장을 S 또는 O로 낮게 예측하는 경향이 나타났으며, 이는 단순 char 기반 딥러닝 모델이 업무상 기밀정보의 의미와 정책 기준을 충분히 학습하지 못했기 때문으로 해석된다.

오분류 결과는 다음 파일로 저장했다.

```text
reports/week8_tensorflow_misclassified.csv
```

추가 분석 결과는 다음 파일로 저장했다.

```text
reports/week8_tensorflow_confusion_matrix.csv
reports/week8_tensorflow_grade_report.csv
```

---

## 7. 저장 모델 테스트 스크립트

`06_test_tensorflow_cso_model.py`는 학습된 모델을 실제 추론용으로 불러오는 테스트 스크립트이다.

이 스크립트를 분리한 이유는 다음과 같다.

```text
학습 스크립트:
데이터 로드 → 모델 학습 → 평가 → 모델 저장

테스트 스크립트:
저장 모델 로드 → 새 문장 입력 → C/S/O 예측
```

실제 서비스 구조에서는 매번 모델을 학습하지 않고, 사전에 학습된 모델을 불러와 예측한다.

따라서 학습 코드와 추론 코드를 분리하는 것이 적절하다.

---

## 8. 판단 보류 로직

Keras 모델의 출력층은 softmax이므로, 의미 없는 입력이 들어와도 C/S/O 중 하나를 반드시 선택한다.

예를 들어 한 글자 입력인 `ㅂ`도 모델은 C/S/O 중 하나로 예측하려고 한다.

이를 방지하기 위해 `06_test_tensorflow_cso_model.py`에는 다음 방어 로직을 추가했다.

```python
MIN_TEXT_LENGTH = 5
CONFIDENCE_THRESHOLD = 0.55
```

적용 기준은 다음과 같다.

| 조건 | 처리 |
|---|---|
| 입력 길이 5자 미만 | 판단 보류 |
| 최고 예측 확률 0.55 미만 | 판단 보류 |
| 기준 충족 | C/S/O 예측 등급 출력 |

확신도가 낮은 경우에는 최종 등급을 단정하지 않고, `suggested_grade`만 참고 등급으로 출력한다.

예시:

```text
문장: 회의 결과를 요약하여 공유드립니다.
예측 등급: 판단 보류
참고 등급: O
판단 사유: 모델 확신도 낮음: 0.419
확률: C=0.169, S=0.412, O=0.419
```

이 로직은 실제 탐지기 적용 시에도 중요하다.

분류 모델은 모르는 입력도 강제로 분류하기 때문에, 최소 입력 길이와 확신도 기준을 두어야 한다.

---

## 9. scikit-learn과 TensorFlow/Keras 비교

`07_compare_sklearn_tensorflow.py`에서는 같은 검증 데이터 기준으로 scikit-learn 모델과 Keras 모델을 비교했다.

비교에 사용한 scikit-learn 모델은 기존 실습에서 사용했던 구조를 기준으로 했다.

```python
model_v2 = Pipeline([
    ("tfidf", TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4)
    )),
    ("clf", LogisticRegression(
        max_iter=1000,
        class_weight="balanced"
    ))
])
```

비교 결과는 다음과 같다.

| 모델 | 정확도 | C 재현율 | S 재현율 | O 재현율 |
|---|---:|---:|---:|---:|
| scikit-learn TF-IDF + LogisticRegression | 0.5405 | 0.2500 | 0.5625 | 0.6923 |
| TensorFlow/Keras char model | 0.5946 | 0.0000 | 0.8750 | 0.6154 |

전체 정확도만 보면 Keras 모델이 더 높았다.

```text
scikit-learn 정확도: 0.5405
Keras 정확도: 0.5946
```

그러나 등급별 재현율을 보면 다른 결론이 나온다.

Keras 모델은 C 등급 재현율이 0.0000이었다.

즉, 검증 데이터의 실제 C등급 8개 중 하나도 C로 예측하지 못했다.

반면 scikit-learn 모델은 전체 정확도는 낮았지만 C 등급을 일부 예측했다.

```text
scikit-learn C 재현율: 0.2500
Keras C 재현율: 0.0000
```

---

## 10. 혼동행렬 비교

scikit-learn 모델의 혼동행렬은 다음과 같다.

| 실제 \ 예측 | C | S | O |
|---|---:|---:|---:|
| C | 2 | 3 | 3 |
| S | 2 | 9 | 5 |
| O | 1 | 3 | 9 |

Keras 모델의 혼동행렬은 다음과 같다.

| 실제 \ 예측 | C | S | O |
|---|---:|---:|---:|
| C | 0 | 4 | 4 |
| S | 0 | 14 | 2 |
| O | 0 | 5 | 8 |

Keras 모델은 검증 데이터에서 C를 한 번도 예측하지 않았다.

예측 등급 분포는 다음과 같다.

| 모델 | C 예측 | S 예측 | O 예측 |
|---|---:|---:|---:|
| scikit-learn | 5 | 15 | 17 |
| Keras | 0 | 23 | 14 |

Keras 모델은 S/O 중심으로 예측이 몰렸고, C 등급 판단에는 취약했다.

---

## 11. scikit-learn 성능 하락 해석

예전 scikit-learn 실험보다 정확도가 낮아진 것은 모델이 갑자기 나빠졌다기보다, 데이터와 예측 문제가 더 어려워졌기 때문으로 해석하는 것이 적절하다.

기존 문제는 다음과 같은 단순 라벨 분류에 가까웠다.

```text
일반 / 개인정보 / 민감정보
```

현재 문제는 다음과 같은 C/S/O 등급 예측이다.

```text
C / S / O
```

C/S/O 등급은 단순 주제 분류가 아니라, 다음 기준이 함께 반영된다.

```text
문장 자체 보호 대상 여부
법령상 민감정보 여부
업무상 민감정보 여부
문서/첨부 확인 신호 여부
보호 필요성
비식별화 필요성
```

따라서 `privacy_sentence_sample_v4.csv` 기준의 C/S/O 예측은 기존 단일 라벨 분류보다 더 어려운 문제이다.

또한 검증 데이터가 37개로 작기 때문에, 몇 개의 오분류만으로 정확도가 크게 변할 수 있다.

따라서 이번 결과는 다음과 같이 해석한다.

```text
라벨 구조가 실무에 가까워지면서 예측 문제가 어려워졌다.
전체 정확도만으로 모델 성능을 판단하기 어렵다.
C 등급 재현율을 반드시 함께 봐야 한다.
```

---

## 12. 모델별 특징 정리

### 12-1. scikit-learn 모델

장점:

```text
작은 데이터에서도 비교적 안정적이다.
C 등급을 일부 예측한다.
TF-IDF 기반 문자 n-gram이 패턴형 표현에 어느 정도 반응한다.
```

한계:

```text
전체 정확도는 낮다.
S/O 경계에서 오분류가 발생한다.
문맥과 정책 기준을 깊게 이해하지 못한다.
```

### 12-2. TensorFlow/Keras 모델

장점:

```text
저장 모델 로드 및 추론 구조를 구현할 수 있다.
S 등급 재현율이 높게 나타났다.
딥러닝 기반 문장분류 흐름을 학습할 수 있다.
```

한계:

```text
데이터가 적어 딥러닝 장점이 충분히 드러나지 않는다.
C 등급을 전혀 예측하지 못했다.
확률이 전반적으로 낮아 판단 보류 로직이 필요하다.
```

---

## 13. 하이브리드 구조와의 관계

이번 비교 결과는 5~6주차에 설계한 하이브리드 구조가 여전히 필요하다는 점을 보여준다.

패턴형 정보나 명확한 C 등급 정보는 AI 모델보다 정규식/규칙 기반 탐지가 더 안정적이다.

예시:

```text
내부 IP
VLAN
포트 정보
장비 취약점
법적 리스크
원가율
계약 단가
장애인 복지카드
질병 치료
```

이런 정보는 AI 모델 단독으로 판단하기보다, 정규식·키워드·업무 규칙 기반 탐지와 결합해야 한다.

권장 구조는 다음과 같다.

```text
정규식/키워드/업무 규칙 탐지
→ C/S 등급 후보 우선 판단

AI 모델
→ 문맥형 S/O 판단 보완
→ 정규식으로 잡기 어려운 표현 보조 탐지

최종 규칙 엔진
→ 등급 병합
→ 조치 방식 결정
→ 위치 정보와 함께 Detection 생성
```

즉, TensorFlow/Keras 모델은 단독 최종 판단기라기보다 하이브리드 탐지 구조의 보조 분류기로 보는 것이 적절하다.

---

## 14. 결론

8주차에서는 TensorFlow/Keras를 사용해 char 단위 C/S/O 등급 예측 모델을 구현했다.

학습, 저장, 추론, 오분류 분석, scikit-learn 비교까지 수행했다.

주요 결과는 다음과 같다.

```text
Keras 검증 정확도: 0.5946
scikit-learn 검증 정확도: 0.5405
Keras C 재현율: 0.0000
scikit-learn C 재현율: 0.2500
```

전체 정확도는 Keras 모델이 높았지만, C 등급을 전혀 예측하지 못했다는 점에서 실무 적용에는 한계가 있었다.

반면 scikit-learn 모델은 전체 정확도는 낮았지만 C 등급을 일부 예측했다.

따라서 현재 데이터 규모와 모델 구조에서는 다음 결론이 적절하다.

```text
1. TensorFlow/Keras 모델은 문장분류 구조 학습에는 유용하다.
2. 현재 수준의 단순 char 모델은 단독 C/S/O 판단기로 사용하기 어렵다.
3. C 등급 탐지는 정규식, 키워드, 업무 규칙 기반 탐지가 반드시 필요하다.
4. AI 모델은 문맥형 S/O 판단과 보조 탐지 역할로 활용하는 것이 적절하다.
5. 최종 탐지기는 정규식 + 규칙 + AI 모델을 결합한 하이브리드 구조가 적합하다.
```

---

## 15. 다음 단계

9주차 이후에는 문장 전체 분류를 넘어 문장 안의 개체를 탐지하는 방향으로 확장한다.

검토 대상은 다음과 같다.

```text
한국어 NER
KLUE-NER
KoBERT / KoELECTRA
Hugging Face 기반 한국어 모델
온프레미스 환경 적용 가능성
```

특히 다음 개체 탐지가 중요하다.

```text
성명
주소
기관명
부서명
문맥상 개인정보
```

다만 9주차 이후에도 C 등급과 업무상 민감정보는 AI 모델만으로 판단하기보다, 정규식·업무 규칙·문서 위치 정보와 함께 결합하는 방향으로 진행하는 것이 적절하다.
