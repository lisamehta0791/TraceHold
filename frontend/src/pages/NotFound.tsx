import { useNavigate } from 'react-router-dom';
import { Button } from '../components/Button';
import { PageHead } from '../components/Page';

export default function NotFound() {
  const nav = useNavigate();
  return (
    <div>
      <PageHead eyebrow="404" title="This page is not in the ledger" lede="The address does not match any TraceHold page." />
      <Button variant="primary" onClick={() => nav('/')}>Back to the home page</Button>
    </div>
  );
}
