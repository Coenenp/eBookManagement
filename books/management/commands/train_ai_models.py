"""Management command to train and manage AI filename recognition models."""

from django.core.management.base import BaseCommand, CommandError
from books.scanner.ai import initialize_ai_system, FilenamePatternRecognizer
from books.models import Book
import json


class Command(BaseCommand):
    help = 'Train and manage AI filename recognition models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['train', 'retrain', 'status', 'test'],
            default='train',
            help='Action to perform (default: train)'
        )

        parser.add_argument(
            '--test-filename',
            type=str,
            help='Test filename for prediction (use with --action test)'
        )

        parser.add_argument(
            '--min-samples',
            type=int,
            default=10,
            help='Minimum number of training samples required (default: 10)'
        )

        parser.add_argument(
            '--use-feedback',
            action='store_true',
            help='Include user feedback data in training'
        )

        parser.add_argument(
            '--min-feedback',
            type=int,
            default=5,
            help='Minimum feedback entries required when using feedback (default: 5)'
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'train':
            self.train_models(options['min_samples'], options.get('use_feedback', False), options.get('min_feedback', 5))
        elif action == 'retrain':
            self.retrain_models(options.get('use_feedback', False), options.get('min_feedback', 5))
        elif action == 'status':
            self.show_status()
        elif action == 'test':
            if not options['test_filename']:
                raise CommandError('--test-filename is required for test action')
            self.test_prediction(options['test_filename'])

    def train_models(self, min_samples, use_feedback=False, min_feedback=5):
        """Train new AI models from scratch."""
        self.stdout.write("🤖 Training AI filename recognition models...")

        try:
            recognizer = FilenamePatternRecognizer()

            # Collect training data
            self.stdout.write("📊 Collecting training data from reviewed books...")
            training_data = recognizer.collect_training_data()

            # Add feedback data if requested
            if use_feedback:
                feedback_data = self._collect_feedback_data(min_feedback)
                if feedback_data:
                    self.stdout.write(f"📝 Adding {len(feedback_data)} feedback samples...")
                    training_data.extend(feedback_data)

            if len(training_data) < min_samples:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  Insufficient training data: {len(training_data)} samples "
                        f"(minimum {min_samples} required)"
                    )
                )
                self.stdout.write(
                    "💡 To get training data, mark some books as 'reviewed' in the admin panel "
                    "after correcting their metadata."
                )
                return

            # Train models
            self.stdout.write(f"🔧 Training models with {len(training_data)} samples...")
            results = recognizer.train_models(training_data)

            if results:
                self.stdout.write(self.style.SUCCESS("✅ AI models trained successfully!"))
                self.stdout.write("\n📈 Training Results:")
                for field, accuracy in results.items():
                    self.stdout.write(f"  • {field.title()}: {accuracy:.1%} accuracy")
            else:
                self.stdout.write(self.style.ERROR("❌ Training failed"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Training error: {e}"))

    def retrain_models(self, use_feedback=False, min_feedback=5):
        """Retrain existing models with optional feedback data."""
        self.stdout.write("🔄 Retraining models...")

        try:
            recognizer = FilenamePatternRecognizer()

            if not recognizer.models_exist():
                self.stdout.write(self.style.WARNING("⚠️  No existing models found. Running initial training..."))
                return self.train_models(10, use_feedback, min_feedback)

            # Collect all available training data
            self.stdout.write("📊 Collecting training data...")
            training_data = recognizer.collect_training_data()

            # Add feedback data if requested
            if use_feedback:
                feedback_data = self._collect_feedback_data(min_feedback)
                if feedback_data:
                    self.stdout.write(f"📝 Adding {len(feedback_data)} feedback samples...")
                    training_data.extend(feedback_data)
                else:
                    self.stdout.write(self.style.WARNING(f"⚠️  No feedback data available (minimum {min_feedback} required)"))
                    return

            if not training_data:
                self.stdout.write(self.style.WARNING("⚠️  No training data available for retraining"))
                return

            # Retrain models
            self.stdout.write(f"� Retraining models with {len(training_data)} samples...")
            results = recognizer.train_models(training_data)

            if results:
                self.stdout.write(self.style.SUCCESS("✅ Models retrained successfully!"))
                self.stdout.write("\n📈 Retraining Results:")
                for field, accuracy in results.items():
                    self.stdout.write(f"  • {field.title()}: {accuracy:.1%} accuracy")

                # Mark feedback as processed if used
                if use_feedback:
                    self._mark_feedback_processed()
            else:
                self.stdout.write(self.style.ERROR("❌ Retraining failed"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Retraining error: {e}"))

    def show_status(self):
        """Show current AI system status."""
        self.stdout.write("📊 AI Filename Recognition System Status\n")

        try:
            recognizer = FilenamePatternRecognizer()

            # Check if models exist
            models_exist = []
            for field in ['title', 'author', 'series', 'volume']:
                if recognizer.model_paths[field].exists():
                    models_exist.append(field)

            if models_exist:
                self.stdout.write(f"✅ Trained models: {', '.join(models_exist)}")

                # Load model metadata if available
                if recognizer.model_paths['metadata'].exists():
                    with open(recognizer.model_paths['metadata'], 'r') as f:
                        metadata = json.load(f)

                    self.stdout.write(f"📅 Training date: {metadata.get('training_date', 'Unknown')}")
                    self.stdout.write(f"📊 Training samples: {metadata.get('training_samples', 'Unknown')}")
                    self.stdout.write(f"🎯 Confidence threshold: {metadata.get('confidence_threshold', 'Unknown')}")

                    if 'model_accuracies' in metadata:
                        self.stdout.write("\n📈 Model Accuracies:")
                        for field, accuracy in metadata['model_accuracies'].items():
                            self.stdout.write(f"  • {field.title()}: {accuracy:.1%}")
            else:
                self.stdout.write("❌ No trained models found")

            # Check training data availability
            reviewed_books = Book.objects.filter(finalmetadata__is_reviewed=True).count()
            self.stdout.write(f"\n📚 Available training data: {reviewed_books} reviewed books")

            # Check feedback data availability
            try:
                from books.models import AIFeedback
                total_feedback = AIFeedback.objects.count()
                pending_feedback = AIFeedback.objects.filter(needs_retraining=True).count()
                self.stdout.write(f"📝 User feedback: {total_feedback} total, {pending_feedback} pending training")
            except ImportError:
                pass  # AIFeedback model not available yet

            if reviewed_books < 10:
                self.stdout.write(
                    self.style.WARNING(
                        "⚠️  Insufficient training data. Need at least 10 reviewed books."
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Status check error: {e}"))

    def test_prediction(self, filename):
        """Test AI prediction on a filename."""
        self.stdout.write(f"🧪 Testing AI prediction for: '{filename}'\n")

        try:
            recognizer = initialize_ai_system()

            if not recognizer:
                self.stdout.write(self.style.ERROR("❌ AI system not available"))
                return

            predictions = recognizer.predict_metadata(filename)

            if predictions:
                self.stdout.write("🔮 AI Predictions:")
                for field, (value, confidence) in predictions.items():
                    confidence_emoji = "🔥" if confidence >= 0.8 else "👍" if confidence >= 0.6 else "🤔"
                    self.stdout.write(
                        f"  • {field.title()}: '{value}' "
                        f"({confidence:.1%} confidence) {confidence_emoji}"
                    )

                is_confident = recognizer.is_prediction_confident(predictions)
                confidence_status = "✅ High confidence" if is_confident else "⚠️  Low confidence"
                self.stdout.write(f"\n{confidence_status}")

            else:
                self.stdout.write("❌ No predictions generated")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Prediction error: {e}"))

    def _collect_feedback_data(self, min_feedback):
        """Collect training data from user feedback."""
        try:
            from books.models import AIFeedback

            feedback_entries = AIFeedback.objects.filter(
                needs_retraining=True
            ).select_related('book')

            if len(feedback_entries) < min_feedback:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  Insufficient feedback data: {len(feedback_entries)} entries "
                        f"(minimum {min_feedback} required)"
                    )
                )
                return []

            training_data = []

            for feedback in feedback_entries:
                try:
                    # Get corrected metadata from feedback
                    corrections = feedback.get_user_corrections_dict()

                    if corrections:
                        # Create training sample from user corrections
                        sample = {
                            'filename': feedback.original_filename,
                            'title': corrections.get('title', ''),
                            'author': corrections.get('author', ''),
                            'series': corrections.get('series', ''),
                            'volume': corrections.get('volume', ''),
                            'source': 'user_feedback',
                            'feedback_rating': feedback.feedback_rating
                        }

                        # Only include samples with sufficient data
                        if sample['title'] or sample['author']:
                            training_data.append(sample)

                except Exception as e:
                    self.stdout.write(f"⚠️  Skipping invalid feedback entry: {e}")
                    continue

            self.stdout.write(f"📝 Collected {len(training_data)} feedback samples")
            return training_data

        except ImportError:
            self.stdout.write(self.style.WARNING("⚠️  AIFeedback model not available"))
            return []
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error collecting feedback: {e}"))
            return []

    def _mark_feedback_processed(self):
        """Mark feedback entries as processed for training."""
        try:
            from books.models import AIFeedback

            updated = AIFeedback.objects.filter(needs_retraining=True).update(
                needs_retraining=False,
                processed_for_training=True
            )

            if updated:
                self.stdout.write(f"✅ Marked {updated} feedback entries as processed")

        except ImportError:
            pass  # AIFeedback model not available yet
        except Exception as e:
            self.stdout.write(f"⚠️  Could not mark feedback as processed: {e}")
