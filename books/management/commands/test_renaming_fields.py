from django.core.management.base import BaseCommand
from books.models import UserProfile, FinalMetadata
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Test the new renaming preference fields'

    def handle(self, *args, **options):
        self.stdout.write("Testing new model fields...")

        # Test UserProfile fields
        user = User.objects.first()
        if user:
            profile = UserProfile.get_or_create_for_user(user)
            self.stdout.write("UserProfile fields test:")
            self.stdout.write(f"  Default folder pattern: {repr(profile.default_folder_pattern)}")
            self.stdout.write(f"  Default filename pattern: {repr(profile.default_filename_pattern)}")
            self.stdout.write(f"  Saved patterns: {profile.saved_patterns}")
            self.stdout.write(f"  Include companion files: {profile.include_companion_files}")

            # Test pattern saving
            profile.save_pattern('Test Pattern', '${author}/${title}', '${title}.${ext}', 'Test description')
            self.stdout.write(f"  After saving pattern: {profile.saved_patterns}")
        else:
            self.stdout.write("No users found")

        # Test FinalMetadata fields
        fm = FinalMetadata.objects.first()
        if fm:
            self.stdout.write("FinalMetadata fields test:")
            self.stdout.write(f"  Is renamed: {fm.is_renamed}")
            self.stdout.write(f"  Final path: {repr(fm.final_path)}")

            # Test Book.effective_path property
            book = fm.book
            self.stdout.write(f"  Book file_path: {repr(book.file_path)}")
            self.stdout.write(f"  Book effective_path: {repr(book.effective_path)}")

        else:
            self.stdout.write("No FinalMetadata found")

        self.stdout.write(self.style.SUCCESS("Test completed successfully!"))
