import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from notebook_rejected_reply import retain_rejected_reply


class RejectedReplyTests(unittest.TestCase):
    def test_interrupted_write_or_sync_leaves_no_final_file_and_allows_later_capture(self):
        real_fdopen=os.fdopen
        for failure in ('write','sync'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as tmp:
                request='notebook-'+'b'*32
                raw=b'{"text":"complete evidence"}'
                class Interrupted:
                    def __init__(self,fd,*args,**kwargs):self.stream=real_fdopen(fd,*args,**kwargs)
                    def __enter__(self):return self
                    def __exit__(self,*args):self.stream.close()
                    def write(self,data):
                        self.stream.write(bytes(data[:4]))
                        raise OSError('interrupted after partial bytes')
                target='notebook_rejected_reply.os.'+('fdopen' if failure=='write' else 'fsync')
                with patch(target,side_effect=Interrupted if failure=='write' else OSError('sync failed')):
                    with self.assertRaises(OSError):retain_rejected_reply(tmp,request,raw)
                self.assertEqual(list((Path(tmp)/'rejected-replies').iterdir()),[])
                retain_rejected_reply(tmp,request,raw)
                self.assertEqual((Path(tmp)/'rejected-replies'/(request+'.json')).read_bytes(),raw)

    def test_short_writes_complete_before_atomic_nonoverwriting_publish(self):
        real_fdopen=os.fdopen;real_link=os.link
        for zero in (False,True):
            with self.subTest(zero=zero),tempfile.TemporaryDirectory() as tmp:
                raw=b'complete bytes';request='notebook-'+'c'*32
                class Short:
                    def __init__(self,fd,*args,**kwargs):self.stream=real_fdopen(fd,*args,**kwargs)
                    def __enter__(self):return self
                    def __exit__(self,*args):self.stream.close()
                    def fileno(self):return self.stream.fileno()
                    def write(self,data):return 0 if zero else self.stream.write(data[:3])
                def publish(source,dest):
                    self.assertEqual(Path(source).read_bytes(),raw)
                    self.assertFalse(Path(dest).exists())
                    return real_link(source,dest)
                with patch('notebook_rejected_reply.os.fdopen',side_effect=Short), \
                     patch('notebook_rejected_reply.os.link',side_effect=publish) as link:
                    if zero:
                        with self.assertRaises(OSError):retain_rejected_reply(tmp,request,raw)
                        link.assert_not_called()
                    else:
                        retain_rejected_reply(tmp,request,raw)
                        link.assert_called_once()
                files=list((Path(tmp)/'rejected-replies').iterdir())
                self.assertEqual(len(files),0 if zero else 1)

    def test_private_exact_write_once_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            request='notebook-'+'a'*32
            raw=b'{"text":"invalid model output"}'
            retain_rejected_reply(tmp,request,raw)
            parent=Path(tmp)/'rejected-replies';target=parent/(request+'.json')
            self.assertEqual(parent.stat().st_mode & 0o777,0o700)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertEqual(target.read_bytes(),raw)
            with self.assertRaises(FileExistsError):retain_rejected_reply(tmp,request,b'changed')
            self.assertEqual(target.read_bytes(),raw)

    def test_bad_identity_size_and_unsafe_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            request='notebook-'+'a'*32
            for identity,raw in (('../escape',b'x'),(request,b''),(request,b'x'*160001),(request,'x')):
                with self.assertRaises(ValueError):retain_rejected_reply(tmp,identity,raw)
            self.assertEqual(list(Path(tmp).iterdir()),[])
            directory=Path(tmp)/'rejected-replies';directory.mkdir(mode=0o755)
            os.chmod(directory,0o755)
            with self.assertRaises(ValueError):retain_rejected_reply(tmp,request,b'x')
            self.assertEqual(list(directory.iterdir()),[])

    def test_symlink_targets_never_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);other=root/'other';other.mkdir()
            directory=root/'rejected-replies';directory.symlink_to(other,target_is_directory=True)
            with self.assertRaises(ValueError):retain_rejected_reply(root,'notebook-'+'a'*32,b'x')
            self.assertEqual(list(other.iterdir()),[])


if __name__=='__main__':unittest.main()
